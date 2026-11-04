"""What the user's portfolio would be worth had they followed each day's plan.

Day by day, starting from the real portfolio of the day each batch of recommendations was made,
cash included (it earns nothing; a position the user sold is cash from then on):

  without following  every position earns its close -> close move (close_return)
  following          a portfolio of its own, carried from day to day from the first day's real one,
                     cash included (none of the user's later trades reach it). Each day, at the open:
                     stops and targets that the overnight gap went through fill there; then that
                     day's plan, built by the same code as "Tu plan de hoy" (app.analysis.rotation)
                     for this portfolio: holdings with a sell signal are sold, buys
                     (sized by the buy panel's rules) are paid with cash first and then by rotating
                     out of weaker positions, and what nothing pays for isn't bought. During the day
                     stops and targets fill at their price; with both inside one candle the stop
                     counts, the worst case. A position with no score that day is kept. Only the
                     plan's own buys carry a stop and a target, like the buy panel's.
  costs              the account's real cost per operation (commission + VAT + market fee, from
                     IOL's order estimate; COMMISSION if IOL can't answer), on every trade

Two references, from the same starting value:
  hold     the starting portfolio, cash included, untouched: no recommendations and none of
           the user's own trades either
  merval   the Merval leaders in equal parts (IOL doesn't publish the index itself)

All of them start from the same value. Positions without prices count as flat. Returns include
dividends on their ex-dates.

Anchored to the real account: "without following" is then the account's actual value each day
(IOL's daily close, and today the same value Mi cartera shows), minus the deposits and plus the
withdrawals made since the start, so moving money in or out is not a gain or a loss. "Following"
starts from that same value and gets the same deposits and withdrawals as cash, taken out of its
value the same way. Without IOL's history, the modeled values above are shown instead.
"""

import logging
import statistics
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from pydantic import BaseModel

from app import prices, universe
from app.analysis import market_hours, risk, rotation, scoring, suitability
from app.brokers.iol import trade_cost_rate
from app.config import get_settings
from app.db import get_db, rows_as
from app.models.db import RecommendationRow
from app.models.iol import DailyBar
from app.portfolio import cash_at
from app.schemas import Transfer
from app.sources.corporate_events import CorporateEvent, events_between

log = logging.getLogger(__name__)

MIN_BARS = 15  # days of prices needed to size a buy, like the buy panel
COMMISSION = 0.006  # fallback when IOL's order estimate is unavailable
CASH = "$cash"  # the account's peso cash, as one more weight


class SimDay(BaseModel):
    day: date
    bought: list[str]
    sold: list[str]
    rotated: list[str] = []  # "TSM>MSFT": sold the first to buy the second
    stopped: list[str] = []  # hit their stop loss
    took_profit: list[str] = []  # hit their take profit
    base_return: float
    follow_return: float
    base_value: float
    follow_value: float
    hold_value: float | None = None
    merval_value: float | None = None


class SeriesStats(BaseModel):
    """One line of the comparison, as the papers report it."""

    total_return: float
    max_drawdown: float  # worst fall from a previous high, <= 0
    sortino: float | None  # mean daily return over its downside deviation


class Simulation(BaseModel):
    start_day: date | None
    start_value: float
    base_value: float
    follow_value: float
    hold_value: float | None = None
    merval_value: float | None = None
    buy_allocation: float  # average share of the portfolio per simulated buy
    commission: float
    days: list[SimDay]
    anchored: bool = False  # True: base values are the real account, net of transfers
    transfers: float = 0.0  # deposits (+) minus withdrawals since the start, taken out of base
    stats: dict[str, SeriesStats] = {}  # follow, base, hold, merval


def _weights_at(when: datetime) -> tuple[float, dict[str, float]]:
    """Total value and per-ticker weights (plus CASH) from the last holdings snapshot before
    `when` (or the first one after it, for days before snapshots started)."""
    db = get_db()
    head = (
        db.table("holdings_snapshots").select("captured_at").lte("captured_at", when.isoformat())
        .order("captured_at", desc=True).limit(1).execute().data
    ) or (
        db.table("holdings_snapshots").select("captured_at").gt("captured_at", when.isoformat())
        .order("captured_at").limit(1).execute().data
    )
    if not head:
        return 0.0, {}
    captured = head[0]["captured_at"]  # type: ignore[index]
    rows = db.table("holdings_snapshots").select("ticker,value").eq("captured_at", captured).execute().data
    values = {str(r["ticker"]): float(r["value"]) for r in rows}  # type: ignore[index, arg-type]
    cash, _ = cash_at(str(captured))
    if cash:
        values[CASH] = cash
    total = sum(values.values())
    return total, ({t: v / total for t, v in values.items()} if total else {})


class _Prices:
    """Daily closes per ticker, loaded once, for the reference portfolios and buy sizing."""

    def __init__(self, start: date):
        self.days = (date.today() - start).days + 40
        self.bars: dict[str, list[DailyBar]] = {}
        # Buys are sized for the user's investor profile, like the buy panel.
        self.risk_per_trade = suitability.RISK_PER_TRADE[suitability.INVESTOR_PROFILE]
        self.max_position = suitability.MAX_POSITION[suitability.INVESTOR_PROFILE]

    def get(self, ticker: str) -> list[DailyBar]:
        if ticker not in self.bars:
            try:
                self.bars[ticker] = prices.daily_bars(ticker, days=self.days)
            except Exception:
                log.warning("no history for %s in the simulation", ticker)
                self.bars[ticker] = []
        return self.bars[ticker]

    def day_return(self, ticker: str, day: date, dividend: float = 0.0) -> float | None:
        """Previous close -> close of `day`, plus any dividend detached that day."""
        bars = self.get(ticker)
        for prev, bar in zip(bars, bars[1:]):
            if bar.day == day and prev.close > 0:
                return bar.close / prev.close - 1 + dividend
        return None

    def bar(self, ticker: str, day: date) -> DailyBar | None:
        return next((b for b in self.get(ticker) if b.day == day and b.close > 0), None)

    def last_close(self, ticker: str, day: date) -> float | None:
        before = [b for b in self.get(ticker) if b.day < day and b.close > 0]
        return before[-1].close if before else None

    def size(self, ticker: str, entry: float, total: float, group_value: float, day: date) -> risk.TradePlan | None:
        """The buy panel's rules, with the prices known before `day`. None without enough of them."""
        before = [b for b in self.get(ticker) if b.day < day and b.close > 0]
        if len(before) < MIN_BARS:
            return None
        atr = risk.atr([b.high for b in before], [b.low for b in before], [b.close for b in before])
        if atr <= 0:
            return None
        volumes = [b.volume for b in before[-20:] if b.volume]
        return risk.plan_buy(
            entry=entry, atr_value=atr, portfolio_value=total, risk_per_trade=self.risk_per_trade,
            cash_available=total,  # the plan decides how each buy is paid
            group_value=group_value, concentration_limit=scoring.CONCENTRATION_LIMIT,
            avg_volume=sum(volumes) / len(volumes) if len(volumes) >= 5 else None,
            max_position=self.max_position,
        )


@dataclass
class Position:
    value: float  # pesos, at `price`
    price: float | None  # the price it was last valued at; None without prices (stays flat)
    stop: float | None = None
    take: float | None = None

    def mark(self, price: float, dividend: float = 0.0) -> None:
        if self.price:
            self.value *= price / self.price + dividend
        self.price = price


@dataclass
class Book:
    """The portfolio that follows the plan."""

    cash: float
    positions: dict[str, Position] = field(default_factory=dict)

    @property
    def total(self) -> float:
        return self.cash + sum(p.value for p in self.positions.values())


@dataclass
class DayTrades:
    bought: dict[str, float] = field(default_factory=dict)  # pesos
    sold: list[str] = field(default_factory=list)
    rotated: list[str] = field(default_factory=list)
    stopped: list[str] = field(default_factory=list)
    took_profit: list[str] = field(default_factory=list)


def opening_price(bar: DailyBar) -> float:
    """The candle's open, kept inside its range: IOL sometimes repeats the previous close there
    (NU on 2026-10-26: open 12.530, high 10.760)."""
    opening = bar.open or bar.close
    if bar.high > 0 and bar.low > 0:
        return max(bar.low, min(bar.high, opening))
    return opening


def mark_open(book: Book, bars: dict[str, DailyBar], events: dict[str, CorporateEvent]) -> None:
    """Take every position through the overnight gap, dividends included."""
    for t, p in book.positions.items():
        bar = bars.get(t)
        if not bar:
            continue
        event = events.get(t)
        if event and event.yield_ is None:
            p.price = opening_price(bar)  # the overnight gap is mostly the coupon detaching
        else:
            p.mark(opening_price(bar), event.yield_ or 0.0 if event else 0.0)


def exit_price(p: Position, bar: DailyBar, at_open: bool) -> tuple[float, str] | None:
    """Where a stop or target fills, if it does: at the open when the gap went through it, else at
    its price. A candle doesn't say which came first, so with both inside it the stop counts."""
    if p.stop is None or p.take is None:
        return None
    if at_open:
        opening = opening_price(bar)
        if opening <= p.stop:
            return opening, "stop"
        if opening >= p.take:
            return opening, "take"
        return None
    if 0 < bar.low <= p.stop:
        return p.stop, "stop"
    if bar.high >= p.take:
        return p.take, "take"
    return None


def _close(book: Book, trades: DayTrades, ticker: str, price: float, kind: str, cost_rate: float) -> None:
    p = book.positions.pop(ticker)
    p.mark(price)
    book.cash += p.value * (1 - cost_rate)
    (trades.stopped if kind == "stop" else trades.took_profit).append(ticker)


def follow_day(
    book: Book,
    bars: dict[str, DailyBar],
    recs: dict[str, RecommendationRow],
    events: dict[str, CorporateEvent],
    cost_rate: float,
    group_of: Callable[[str], str],
    size: Callable[[str, float, float, float], risk.TradePlan | None],
) -> DayTrades:
    """One day of the portfolio that follows the plan, open to close. Updates `book`.

    What a recommendation said depended on the real portfolio, so buy or sell is decided again for
    this one, from its score and its place in the ranking."""
    trades = DayTrades()

    # Overnight, then whatever the gap went through.
    mark_open(book, bars, events)
    gone = set()
    for t in list(book.positions):
        bar = bars.get(t)
        hit = exit_price(book.positions[t], bar, at_open=True) if bar else None
        if hit:
            _close(book, trades, t, hit[0], hit[1], cost_rate)
            gone.add(t)

    # The plan, at the open. Only what traded that day can be traded.
    total = book.total
    groups: dict[str, float] = defaultdict(float)
    for t, p in book.positions.items():
        groups[group_of(t)] += p.value

    def score(t: str) -> float:
        return recs[t].score - recs[t].signal_breakdown.concentration if t in recs else 0.0  # first model

    held = [
        rotation.Held(
            ticker=t, score=score(t), value=p.value, quantity=p.value,
            action="sell" if t in recs and scoring.is_sell_signal(recs[t]) else "keep",
            out_of_profile=bool(t in recs and recs[t].signal_breakdown.out_of_profile),
        )
        for t, p in book.positions.items() if t in bars and p.value > 0
    ]
    candidates = []
    plans: dict[str, risk.TradePlan] = {}
    for t, r in recs.items():
        bar = bars.get(t)
        if t in book.positions or t in gone or not bar or not scoring.is_buy_signal(r):
            continue
        opening = opening_price(bar)
        sized = size(t, opening, total, groups[group_of(t)])
        if sized:
            plans[t] = sized
            candidates.append(rotation.Candidate(t, score(t), 1.0, sized.quantity * opening))  # in pesos

    plan = rotation.build(book.cash, total, held, candidates, cost_rate)
    bought: dict[str, float] = defaultdict(float)
    leftover = 0.0
    for step in plan.steps:
        if step.action == "buy":
            bought[step.ticker] += step.amount
            continue
        p = book.positions[step.ticker]
        p.value -= step.amount
        trades.sold.append(step.ticker)
        if step.pair:
            trades.rotated.append(f"{step.ticker}>{step.pair}")
        if p.value < 1:  # what rounding left behind
            leftover += p.value
            del book.positions[step.ticker]
    book.cash = min(book.cash, 0.0) + plan.cash_left + leftover  # a withdrawal can leave it below zero
    for t, amount in bought.items():
        opening = opening_price(bars[t])
        book.positions[t] = Position(amount * (1 - cost_rate), opening, plans[t].stop_loss, plans[t].take_profit)
    trades.bought = dict(bought)

    # During the day.
    for t in list(book.positions):
        bar = bars.get(t)
        if not bar:
            continue
        hit = exit_price(book.positions[t], bar, at_open=False)
        if hit:
            _close(book, trades, t, hit[0], hit[1], cost_rate)
        else:
            book.positions[t].mark(bar.close)
    return trades


@dataclass
class _Account:
    """The real account from the day before the simulation starts."""

    ref_day: date
    start: float
    closes: dict[date, float]
    moved: list[Transfer]
    live: float
    today: date


def _load_account(first: date) -> _Account | None:
    from app import account  # avoid an import cycle

    today = market_hours.now_art().date()
    closes = account.daily(first - timedelta(days=10), today - timedelta(days=1))
    before = [d for d in closes if d < first]
    if not before:
        return None
    ref_day = max(before)
    return _Account(ref_day, closes[ref_day], closes, account.transfers(ref_day, today), account.current().total, today)


def simulate() -> Simulation:
    recs = rows_as(
        RecommendationRow,
        get_db().table("recommendations").select("*").eq("kind", "daily")
        .not_.is_("evaluated_at", "null").order("target_date").execute().data,
    )
    by_day: dict[date, list[RecommendationRow]] = defaultdict(list)
    for r in recs:
        by_day[r.target_date].append(r)

    real_rate = trade_cost_rate()
    cost_rate = COMMISSION if real_rate is None else real_rate
    px = _Prices(min(by_day) if by_day else date.today())
    try:
        events = events_between(min(by_day) if by_day else date.today(), date.today())
    except Exception:
        log.warning("no corporate events for the simulation")
        events = {}
    dividends = {k: e.yield_ or 0.0 for k, e in events.items() if e.kind == "dividend"}
    groups = universe.groups()

    base_value = follow_value = start_value = 0.0
    book = Book(cash=0.0)
    real: _Account | None = None
    moved_until: date | None = None
    moved_total = 0.0  # deposits minus withdrawals the book has received
    hold = Book(cash=0.0)  # the starting portfolio, untouched
    last_session: date | None = None
    merval_value: float | None = None
    start_day: date | None = None
    allocations: list[float] = []
    days: list[SimDay] = []

    for day in sorted(by_day):
        batch = by_day[day]
        total, weights = _weights_at(max(r.created_at for r in batch))
        if not weights:
            continue
        if start_day is None:
            start_day, start_value = day, total
            base_value = follow_value = total
            merval_value = total
            try:
                real = _load_account(day)
            except Exception:
                log.exception("could not load the real account for the simulation")
            scale = real.start / total if real else 1.0
            follow_value = total * scale
            moved_until = real.ref_day if real else None
            for t, w in weights.items():
                if t == CASH:
                    book.cash = w * total * scale
                    hold.cash = w * total
                else:
                    book.positions[t] = Position(w * total * scale, px.last_close(t, day))
                    hold.positions[t] = Position(w * total, px.last_close(t, day))

        recs = {r.ticker: r for r in batch}
        close_to_close = {r.ticker: r.close_return or 0.0 for r in batch}

        # Cash earns nothing, so it adds nothing to the day's return but weighs in the total.
        base_r = sum(w * close_to_close.get(t, 0.0) for t, w in weights.items() if t != CASH)

        # A session nobody graded (a job failed that day) has no plan, but stops still fire and
        # prices still move.
        sessions = [day]
        if last_session:
            sessions = sorted({
                b.day for t in book.positions for b in px.get(t) if last_session < b.day < day
            }) + sessions
        last_session = day
        trades = DayTrades()
        for session in sessions:
            # Following: the real deposits and withdrawals arrive as cash and don't count as results.
            if real and moved_until:
                arrived = sum(t.amount for t in real.moved if moved_until < t.day <= session)
                book.cash += arrived
                moved_total += arrived
                moved_until = session
            day_events = {t: e for (t, d), e in events.items() if d == session}
            session_recs = recs if session == day else {}
            bars = {t: bar for t in set(book.positions) | set(session_recs) if (bar := px.bar(t, session))}
            value_at_start = book.total
            done = follow_day(
                book, bars, session_recs, day_events, cost_rate,
                lambda t: scoring.risk_group(t, groups.stocks, groups.bonds),
                lambda t, entry, total, group_value: px.size(t, entry, total, group_value, session),
            )
            allocations += [v / value_at_start for v in done.bought.values()] if value_at_start else []
            trades.bought |= done.bought
            trades.sold += done.sold
            trades.rotated += done.rotated
            trades.stopped += done.stopped
            trades.took_profit += done.took_profit

            # References.
            hold_bars = {t: bar for t in hold.positions if (bar := px.bar(t, session))}
            mark_open(hold, hold_bars, day_events)
            for t, bar in hold_bars.items():
                hold.positions[t].mark(bar.close)
            leaders = [x for x in (px.day_return(t, session, dividends.get((t, session), 0.0)) for t in sorted(groups.leaders))
                       if x is not None]
            if merval_value is not None and leaders:
                merval_value *= 1 + statistics.mean(leaders)

        follow_net = book.total - moved_total
        follow_r = follow_net / follow_value - 1 if follow_value else 0.0
        follow_value = follow_net

        base_value *= 1 + base_r
        days.append(SimDay(
            day=day, bought=sorted(trades.bought), sold=sorted(set(trades.sold)), rotated=sorted(set(trades.rotated)),
            stopped=sorted(trades.stopped), took_profit=sorted(trades.took_profit), base_return=round(base_r, 6),
            follow_return=round(follow_r, 6), base_value=round(base_value, 2),
            follow_value=round(follow_value, 2), hold_value=round(hold.total, 2),
            merval_value=round(merval_value, 2) if merval_value is not None else None,
        ))

    sim = Simulation(
        start_day=start_day, start_value=round(start_value, 2), base_value=round(base_value, 2),
        follow_value=round(follow_value, 2),
        hold_value=round(hold.total, 2) if days else None,
        merval_value=round(merval_value, 2) if merval_value is not None else None,
        buy_allocation=round(statistics.mean(allocations), 4) if allocations else 0.0,
        commission=cost_rate, days=days,
    )
    sim = _anchor_to_account(sim, real) if real else sim
    return sim.model_copy(update={"stats": _stats(sim)})


def series_stats(values: list[float], start: float) -> SeriesStats | None:
    if not values or start <= 0:
        return None
    series = [start, *values]
    returns = [b / a - 1 for a, b in zip(series, series[1:]) if a > 0]
    peak, drawdown = series[0], 0.0
    for v in series:
        peak = max(peak, v)
        drawdown = min(drawdown, v / peak - 1)
    downside = (sum(min(r, 0.0) ** 2 for r in returns) / len(returns)) ** 0.5
    return SeriesStats(
        total_return=round(values[-1] / start - 1, 6), max_drawdown=round(drawdown, 6),
        sortino=round(statistics.mean(returns) / downside, 4) if downside > 0 else None,
    )


def _stats(sim: Simulation) -> dict[str, SeriesStats]:
    series = {
        "follow": [d.follow_value for d in sim.days], "base": [d.base_value for d in sim.days],
        "hold": [d.hold_value for d in sim.days if d.hold_value is not None],
        "merval": [d.merval_value for d in sim.days if d.merval_value is not None],
    }
    return {k: s for k, v in series.items() if (s := series_stats(v, sim.start_value))}


def _anchor_to_account(sim: Simulation, acct: _Account) -> Simulation:
    """Replace "without following" with the account's real value, net of transfers. "Following"
    already started from it. See the module docstring."""
    if not sim.days:
        return sim

    def real(day: date) -> float | None:
        value = acct.live if day >= acct.today else acct.closes.get(day)
        if value is None:
            return None
        return value - sum(t.amount for t in acct.moved if acct.ref_day < t.day <= day)

    scale = acct.start / sim.start_value if sim.start_value else 1.0
    base_prev = acct.start
    days = []
    for d in sim.days:
        r = real(d.day)
        if r is None:
            r = base_prev * (1 + d.base_return)
        days.append(d.model_copy(update={
            "base_return": round(r / base_prev - 1, 6), "base_value": round(r, 2),
            "hold_value": round(d.hold_value * scale, 2) if d.hold_value is not None else None,
            "merval_value": round(d.merval_value * scale, 2) if d.merval_value is not None else None,
        }))
        base_prev = r
    last = days[-1]
    return sim.model_copy(update={
        "start_value": round(acct.start, 2), "base_value": last.base_value,
        "hold_value": last.hold_value, "merval_value": last.merval_value, "days": days,
        "transfers": round(sum(t.amount for t in acct.moved if acct.ref_day < t.day <= last.day), 2),
        "anchored": True,
    })
