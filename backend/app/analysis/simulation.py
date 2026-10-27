"""What the user's portfolio would be worth had they followed every daily recommendation.

Day by day, starting from the real portfolio of the day each batch of recommendations was made,
cash included (it earns nothing; a position the user sold is cash from then on):

  without following  every position earns its close -> close move (close_return)
  following          positions marked "sell" are sold at the next open (so they still take the
                     overnight gap) and sit in cash for the day; every "buy" is sized like the
                     buy panel sizes it (losing RISK_PER_TRADE of the portfolio at a 2 ATR stop,
                     between MIN_ALLOCATION and MAX_POSITION; BUY_ALLOCATION without price
                     history) at the next open (earning open -> close), paid with cash first
                     (including what the sells raised) and the rest taken pro rata from the
                     positions; "keep" changes nothing
  costs              the account's real cost per operation (commission + VAT + market fee, from
                     IOL's order estimate; COMMISSION if IOL can't answer), charged only when
                     something changes versus the
                     previous day (entering or leaving a buy, selling or buying back)

Two references, from the same starting value:
  hold     the starting portfolio, cash included, untouched: no recommendations and none of
           the user's own trades either
  merval   the Merval leaders in equal parts (IOL doesn't publish the index itself)

All of them compound from the same starting value, so the difference between "without" and
"following" is the effect of following the recommendations. Positions without a graded move
count as flat. Returns include dividends on their ex-dates.
"""

import logging
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta

from pydantic import BaseModel

from app import prices
from app.analysis import risk
from app.analysis.tagger import UNIVERSE
from app.brokers.iol import trade_cost_rate
from app.config import get_settings
from app.db import get_db, rows_as
from app.models.db import RecommendationRow
from app.models.iol import DailyBar
from app.portfolio import cash_at
from app.sources.corporate_events import events_between

log = logging.getLogger(__name__)

BUY_ALLOCATION = 0.05  # when there is no price history to size from
MIN_ALLOCATION = 0.01
COMMISSION = 0.006  # fallback when IOL's order estimate is unavailable
CASH = "$cash"  # the account's peso cash, as one more weight


class SimDay(BaseModel):
    day: date
    bought: list[str]
    sold: list[str]
    base_return: float
    follow_return: float
    base_value: float
    follow_value: float
    hold_value: float | None = None
    merval_value: float | None = None


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

    def allocation(self, ticker: str, day: date) -> float:
        """Share of the portfolio a buy gets, sized like the buy panel does."""
        before = [b for b in self.get(ticker) if b.day < day]
        if len(before) < 15 or before[-1].close <= 0:
            return BUY_ALLOCATION
        atr = risk.atr([b.high for b in before], [b.low for b in before], [b.close for b in before])
        stop = 2 * atr / before[-1].close
        if stop <= 0:
            return BUY_ALLOCATION
        return max(MIN_ALLOCATION, min(risk.MAX_POSITION, get_settings().risk_per_trade / stop))


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
        dividends = {k: e.yield_ or 0.0 for k, e in events_between(
            min(by_day) if by_day else date.today(), date.today()).items() if e.kind == "dividend"}
    except Exception:
        log.warning("no corporate events for the simulation")
        dividends = {}

    base_value = follow_value = start_value = 0.0
    hold: dict[str, float] = {}  # starting portfolio, value per ticker
    merval_value: float | None = None
    start_day: date | None = None
    prev_buys: set[str] = set()
    prev_sells: set[str] = set()
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
            hold = {t: w * total for t, w in weights.items()}
            merval_value = total

        close_to_close = {r.ticker: r.close_return or 0.0 for r in batch}
        open_to_close = {r.ticker: r.realized_return or 0.0 for r in batch}
        # Overnight gap: what a position goes through before it can be sold at the open.
        gap = {t: (1 + close_to_close[t]) / (1 + open_to_close[t]) - 1 for t in close_to_close}
        buys = {r.ticker for r in batch if r.action == "buy" and r.ticker not in weights}
        sells = {r.ticker for r in batch if r.action == "sell" and r.ticker in weights}
        sizes = {t: px.allocation(t, day) for t in buys}
        allocations += sizes.values()

        # Cash earns nothing, so it adds nothing to the day's return but weighs in the total.
        base_r = sum(w * close_to_close.get(t, 0.0) for t, w in weights.items() if t != CASH)

        # Following: sold positions only take the overnight gap and become cash; buys enter at
        # the open, paid with cash first and then pro rata from the positions.
        kept_r = base_r - sum(weights[t] * (close_to_close.get(t, 0.0) - gap.get(t, 0.0)) for t in sells)
        invested = min(1.0, sum(sizes.values()))
        cash_w = weights.get(CASH, 0.0) + sum(weights[t] for t in sells)
        from_positions = max(0.0, invested - cash_w)
        held_w = 1 - cash_w
        kept_share = 1 - from_positions / held_w if held_w > 0 else 0.0
        follow_r = kept_share * kept_r + sum(sizes[t] * open_to_close.get(t, 0.0) for t in buys)

        # Commissions only on changes versus yesterday.
        trades = (
            sum(sizes.get(t, BUY_ALLOCATION) for t in buys ^ prev_buys)
            + sum(weights.get(t, 0.0) for t in sells ^ prev_sells)
        )
        follow_r -= trades * cost_rate

        # References: graded moves where there are any, otherwise the cached closes.
        for t in hold:
            if t == CASH:
                continue
            r = close_to_close.get(t)
            if r is None:
                r = px.day_return(t, day, dividends.get((t, day), 0.0)) or 0.0
            hold[t] *= 1 + r
        leaders = [x for x in (px.day_return(t, day, dividends.get((t, day), 0.0)) for t in UNIVERSE["acciones"])
                   if x is not None]
        if merval_value is not None and leaders:
            merval_value *= 1 + statistics.mean(leaders)

        base_value *= 1 + base_r
        follow_value *= 1 + follow_r
        days.append(SimDay(
            day=day, bought=sorted(buys), sold=sorted(sells), base_return=round(base_r, 6),
            follow_return=round(follow_r, 6), base_value=round(base_value, 2),
            follow_value=round(follow_value, 2), hold_value=round(sum(hold.values()), 2),
            merval_value=round(merval_value, 2) if merval_value is not None else None,
        ))
        prev_buys, prev_sells = buys, sells

    return Simulation(
        start_day=start_day, start_value=round(start_value, 2), base_value=round(base_value, 2),
        follow_value=round(follow_value, 2),
        hold_value=round(sum(hold.values()), 2) if hold else None,
        merval_value=round(merval_value, 2) if merval_value is not None else None,
        buy_allocation=round(statistics.mean(allocations), 4) if allocations else BUY_ALLOCATION,
        commission=cost_rate, days=days,
    )
