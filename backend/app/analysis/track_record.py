"""Grades each daily recommendation against the close of its target day.

A recommendation made after the close of day D is priced at D's close and graded on D+1's
close (realized_return = close(D+1) / close(D) - 1):

  buy   right if the price went up
  sell  right if the price went down
  keep  right if the price moved less than KEEP_BAND either way (no big move missed)
"""

import logging
from collections import defaultdict
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone

from app.analysis import market_hours
from app import prices
from app.db import get_db, rows_as
from app.models.db import Action, RecommendationRow
from app.schemas import HitStats, TrackRecordSummary

log = logging.getLogger(__name__)

KEEP_BAND = 0.015
# After this many days without a price for the target day (holiday, suspended ticker),
# give up and mark it evaluated with no result.
GIVE_UP_AFTER_DAYS = 5


def close_on(ticker: str, day: date) -> float | None:
    return prices.close_on(ticker, day)


def is_hit(action: Action, ret: float) -> bool:
    if action == "buy":
        return ret > 0
    if action == "sell":
        return ret < 0
    return abs(ret) < KEEP_BAND


def evaluate_pending(
    now: datetime | None = None, close_fn: Callable[[str, date], float | None] = close_on
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
            close = close_fn(rec.ticker, rec.target_date)
        except Exception:
            log.exception("no close for %s on %s", rec.ticker, rec.target_date)
            close = None
        if close is None or not rec.price_at_rec:
            if (now.date() - rec.target_date).days < GIVE_UP_AFTER_DAYS:
                continue  # try again on the next run
        else:
            ret = close / rec.price_at_rec - 1
            fields |= {
                "close_on_target": close,
                "realized_return": round(ret, 6),
                "hit": is_hit(rec.action, ret),
            }
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
