"""Grades each daily recommendation against its target day.

A recommendation made after the close of day D can only be acted on at the open of D+1, so it
is graded on that day's open -> close (realized_return = close(D+1) / open(D+1) - 1). The
close -> close move is kept too (close_return), for positions already held overnight.

  buy   right if the price went up
  sell  right if the price went down
  keep  for a position the user holds: right unless it fell more than KEEP_BAND (selling
        would have been better); for one they don't hold: right unless it rose more than
        KEEP_BAND (buying would have been better)
"""

import logging
from collections import defaultdict
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone

from app.analysis import market_hours
from app import prices
from app.db import get_db, rows_as
from app.models.db import Action, RecommendationRow
from app.models.iol import DailyBar
from app.schemas import HitStats, SignalStats, TrackRecordSummary

log = logging.getLogger(__name__)

KEEP_BAND = 0.015
# After this many days without a price for the target day (holiday, suspended ticker),
# give up and mark it evaluated with no result.
GIVE_UP_AFTER_DAYS = 5


def bar_on(ticker: str, day: date) -> DailyBar | None:
    return prices.bar_on(ticker, day)


def is_hit(action: Action, ret: float, held: bool) -> bool:
    if action == "buy":
        return ret > 0
    if action == "sell":
        return ret < 0
    return ret > -KEEP_BAND if held else ret < KEEP_BAND


def _grade(rec: RecommendationRow, bar: DailyBar) -> dict[str, str | float | bool | None]:
    ret = bar.close / bar.open - 1 if bar.open else 0.0
    return {
        "open_on_target": bar.open,
        "close_on_target": bar.close,
        "realized_return": round(ret, 6),
        "close_return": round(bar.close / rec.price_at_rec - 1, 6) if rec.price_at_rec else None,
        "hit": is_hit(rec.action, ret, rec.held),
    }


def regrade_all(bar_fn: Callable[[str, date], DailyBar | None] = bar_on) -> int:
    """Re-grade every graded recommendation with the current rules."""
    db = get_db()
    rows = rows_as(
        RecommendationRow,
        db.table("recommendations").select("*").eq("kind", "daily")
        .not_.is_("evaluated_at", "null").execute().data,
    )
    changed = 0
    for r in rows:
        bar = bar_fn(r.ticker, r.target_date)
        if bar:
            db.table("recommendations").update(_grade(r, bar)).eq("id", r.id).execute()
            changed += 1
    return changed


def evaluate_pending(
    now: datetime | None = None, bar_fn: Callable[[str, date], DailyBar | None] = bar_on
) -> int:
    """Grade daily recommendations whose target day has closed. Returns how many were graded."""
    now = (now or market_hours.now_art()).astimezone(market_hours.ART)
    last_closed = now.date() if now.time() >= market_hours.CLOSE else now.date() - timedelta(days=1)
    db = get_db()
    pending = rows_as(
        RecommendationRow,
        db.table("recommendations").select("*").eq("kind", "daily").is_("evaluated_at", "null")
        .lte("target_date", last_closed.isoformat()).execute().data,
    )
    graded = 0
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
            fields |= _grade(rec, bar)
            graded += 1
        db.table("recommendations").update(fields).eq("id", rec.id).execute()
    log.info("graded %d recommendations", graded)
    return graded


def _bucket(confidence: float) -> str:
    return "alta (>=0.6)" if confidence >= 0.6 else "media (0.3-0.6)" if confidence >= 0.3 else "baja (<0.3)"


def _stats(rs: list[RecommendationRow]) -> HitStats:
    n = len(rs)
    hits = sum(1 for r in rs if r.hit)
    avg = sum(r.realized_return or 0 for r in rs) / n if n else None
    return HitStats(
        n=n, hits=hits, hit_rate=round(hits / n, 3) if n else None,
        avg_return=round(avg, 5) if avg is not None else None,
    )


def summary() -> TrackRecordSummary:
    """Hit rate overall and by action, main driver, confidence and held vs not held."""
    rows = rows_as(
        RecommendationRow,
        get_db().table("recommendations").select("*").eq("kind", "daily")
        .not_.is_("hit", "null").execute().data,
    )
    action: dict[Action, list[RecommendationRow]] = defaultdict(list)
    driver: dict[str, list[RecommendationRow]] = defaultdict(list)
    confidence: dict[str, list[RecommendationRow]] = defaultdict(list)
    held: dict[str, list[RecommendationRow]] = defaultdict(list)
    for r in rows:
        action[r.action].append(r)
        driver[r.driver or "trend"].append(r)
        confidence[_bucket(r.confidence)].append(r)
        held["en cartera" if r.held else "fuera de cartera"].append(r)
    return TrackRecordSummary(
        overall=_stats(rows),
        action={k: _stats(v) for k, v in action.items()},
        driver={k: _stats(v) for k, v in driver.items()},
        confidence={k: _stats(v) for k, v in confidence.items()},
        held={k: _stats(v) for k, v in held.items()},
    )


SIGNALS = ("news", "markets", "trend", "context", "gap")
SIGNAL_MIN = 0.05  # a component smaller than this didn't really point anywhere


def signal_stats() -> list[SignalStats]:
    """For each score component: how often its sign matched the next day's open -> close move."""
    rows = rows_as(
        RecommendationRow,
        get_db().table("recommendations").select("*").eq("kind", "daily")
        .not_.is_("realized_return", "null").execute().data,
    )
    out = []
    for name in SIGNALS:
        ups: list[float] = []
        downs: list[float] = []
        for r in rows:
            value = getattr(r.signal_breakdown, name)
            if abs(value) < SIGNAL_MIN or r.realized_return is None:
                continue
            (ups if value > 0 else downs).append(r.realized_return)
        n = len(ups) + len(downs)
        hits = sum(1 for x in ups if x > 0) + sum(1 for x in downs if x < 0)
        out.append(SignalStats(
            signal=name, n=n, hits=hits, hit_rate=round(hits / n, 3) if n else None,
            avg_when_up=round(sum(ups) / len(ups), 5) if ups else None,
            avg_when_down=round(sum(downs) / len(downs), 5) if downs else None,
        ))
    return out
