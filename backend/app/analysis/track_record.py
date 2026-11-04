"""Grades each daily recommendation against its target day.

Recommendations are issued just before the open, so each is graded on that day's open -> close
(realized_return = close / open - 1). The close -> close move is kept too (close_return), for
positions already held overnight.

What counts is the excess: its return minus the day's median of its asset class (excess_return).
Whether the whole market rose or fell says nothing about the recommendation.

  buy   right if it beat its class that day
  sell  right if it lagged its class
  keep  no verdict: staying put isn't a call

Dividends and coupons: the price drops overnight on an ex-date, which open -> close doesn't
see but close -> close does. So on an ex-date the dividend yield is added back to close_return
(total return); for a coupon of unknown size, close_return is replaced by open -> close.
"""

import logging
import statistics
from collections import defaultdict
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone

from app import prices, universe
from app.analysis import market_hours, scoring
from app.db import get_db, rows_as
from app.models.db import Action, RecommendationRow, SignalBreakdown
from app.models.iol import DailyBar
from app.schemas import SignalStats
from app.sources.corporate_events import CorporateEvent, events_between

log = logging.getLogger(__name__)

# After this many days without a price for the target day (holiday, suspended ticker),
# give up and mark it evaluated with no result.
GIVE_UP_AFTER_DAYS = 5
MIN_IN_CLASS = 3  # below this, the day's median of a class says nothing


def bar_on(ticker: str, day: date) -> DailyBar | None:
    return prices.bar_on(ticker, day)


def is_hit(action: Action, excess: float) -> bool | None:
    if action == "buy":
        return excess > 0
    if action == "sell":
        return excess < 0
    return None


def asset_class(r: RecommendationRow) -> str:
    if r.signal_breakdown.asset_class:
        return r.signal_breakdown.asset_class
    g = universe.groups()  # the first model didn't save it
    return "stocks" if r.ticker in g.stocks else "bonds" if r.ticker in g.bonds else "us"


def excess_returns(rows: list[RecommendationRow]) -> dict[str, float]:
    """id -> realized return minus the median of its class that day."""
    groups: dict[tuple[date, str], list[RecommendationRow]] = defaultdict(list)
    for r in rows:
        if r.realized_return is not None:
            groups[(r.target_date, asset_class(r))].append(r)
    out: dict[str, float] = {}
    for rs in groups.values():
        if len(rs) >= MIN_IN_CLASS:
            median = statistics.median(r.realized_return or 0.0 for r in rs)
            out.update({r.id: (r.realized_return or 0.0) - median for r in rs})
    return out


def _grade(
    rec: RecommendationRow, bar: DailyBar, event: CorporateEvent | None = None
) -> dict[str, str | float | bool | None]:
    ret = bar.close / bar.open - 1 if bar.open else 0.0
    close_ret = bar.close / rec.price_at_rec - 1 if rec.price_at_rec else None
    event_yield = None
    if event and close_ret is not None:
        if event.yield_ is not None:
            event_yield = event.yield_
            close_ret += event.yield_
        else:
            close_ret = ret  # the overnight gap is mostly the coupon detaching
    return {
        "open_on_target": bar.open,
        "close_on_target": bar.close,
        "realized_return": round(ret, 6),
        "close_return": round(close_ret, 6) if close_ret is not None else None,
        "event_yield": round(event_yield, 6) if event_yield is not None else None,
    }


def _events_for(rows: list[RecommendationRow]) -> dict[tuple[str, date], CorporateEvent]:
    if not rows:
        return {}
    try:
        return events_between(min(r.target_date for r in rows), max(r.target_date for r in rows))
    except Exception:
        log.exception("could not load corporate events; grading without them")
        return {}


def graded_daily(version: int | None = None) -> list[RecommendationRow]:
    """Every graded daily recommendation, oldest first."""
    out: list[RecommendationRow] = []
    page = 0
    while True:  # PostgREST returns at most 1000 rows per request
        q = get_db().table("recommendations").select("*").eq("kind", "daily").not_.is_("realized_return", "null")
        if version is not None:
            q = q.eq("model_version", version)
        batch = rows_as(RecommendationRow, q.order("target_date").order("id").range(page * 1000, page * 1000 + 999).execute().data)
        out += batch
        if len(batch) < 1000:
            return out
        page += 1


def update_excess(days: set[date] | None = None) -> None:
    """Save each recommendation's excess and verdict. It takes the whole day's batch graded."""
    rows = graded_daily()
    if days is not None:
        rows = [r for r in rows if r.target_date in days]
    excess = excess_returns(rows)
    db = get_db()
    for r in rows:
        value = excess.get(r.id)
        db.table("recommendations").update({
            "excess_return": round(value, 6) if value is not None else None,
            "hit": is_hit(r.action, value) if value is not None else None,
        }).eq("id", r.id).execute()


def regrade_all(bar_fn: Callable[[str, date], DailyBar | None] = bar_on) -> int:
    """Re-grade every graded recommendation with the current rules."""
    db = get_db()
    rows = graded_daily()
    events = _events_for(rows)
    changed = 0
    for r in rows:
        bar = bar_fn(r.ticker, r.target_date)
        if bar:
            grade = _grade(r, bar, events.get((r.ticker, r.target_date)))
            db.table("recommendations").update(grade).eq("id", r.id).execute()
            changed += 1
    update_excess()
    return changed


def evaluate_pending(
    now: datetime | None = None, bar_fn: Callable[[str, date], DailyBar | None] = bar_on
) -> int:
    """Grade daily recommendations whose target day has closed. Returns how many were graded."""
    now = (now or market_hours.now_art()).astimezone(market_hours.ART)
    last_closed = now.date() if now.time() >= market_hours.SETTLED else now.date() - timedelta(days=1)
    db = get_db()
    pending = rows_as(
        RecommendationRow,
        db.table("recommendations").select("*").eq("kind", "daily").is_("evaluated_at", "null")
        .lte("target_date", last_closed.isoformat()).execute().data,
    )
    events = _events_for(pending)
    graded = 0
    days: set[date] = set()
    for rec in pending:
        fields: dict[str, str | float | bool | None] = {"evaluated_at": datetime.now(timezone.utc).isoformat()}
        try:
            bar = bar_fn(rec.ticker, rec.target_date)
        except Exception:
            log.exception("no prices for %s on %s", rec.ticker, rec.target_date)
            bar = None
        if bar is None:
            if (now.date() - rec.target_date).days < GIVE_UP_AFTER_DAYS:
                continue  # try again on the next run
        else:
            fields |= _grade(rec, bar, events.get((rec.ticker, rec.target_date)))
            graded += 1
            days.add(rec.target_date)
        db.table("recommendations").update(fields).eq("id", rec.id).execute()
    if days:
        update_excess(days)
    log.info("graded %d recommendations", graded)
    return graded


SIGNALS = ("news", "markets", "macro")
IN_SCORE = {"news", "markets"}
SIGNAL_MIN = 0.05  # smaller than this didn't really point anywhere


def _signal_value(b: SignalBreakdown, name: str) -> float:
    return getattr(b, name)


def signal_stats(rows: list[RecommendationRow] | None = None) -> list[SignalStats]:
    """For each signal: how often the asset beat or lagged its class that day as it said. Only
    recommendations of this model: the first one's tags meant something else."""
    if rows is None:
        rows = graded_daily(scoring.MODEL_VERSION)
    out = []
    for name in SIGNALS:
        n = hits = 0
        days: set[date] = set()
        for r in rows:
            value = _signal_value(r.signal_breakdown, name)
            if abs(value) < SIGNAL_MIN or not r.excess_return:
                continue
            n += 1
            hits += (value > 0) == (r.excess_return > 0)
            days.add(r.target_date)
        out.append(SignalStats(
            signal=name, in_score=name in IN_SCORE, n=n, hits=hits,  # type: ignore[arg-type]
            rate=round(hits / n, 3) if n else None, days=len(days),
        ))
    return out
