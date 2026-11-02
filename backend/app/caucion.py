"""Caución for the pesos the day's plan leaves idle: only a suggestion, nothing is placed.

Uses the shortest term, so the money is back the next business day. IOL quotes rates only while
the market is open; the last rate seen is kept for the rest of the time and shown as such.
"""

import logging
from datetime import datetime, timedelta, timezone

from app.analysis import market_hours
from app.brokers.iol import get_iol
from app.db import get_db
from app.schemas import CaucionSuggestion

log = logging.getLogger(__name__)

CACHE_KEY = "caucion_rate"
MAX_RATE_AGE = timedelta(days=4)  # covers a long weekend


def annual_rate(quoted: float) -> float:
    """IOL's docs say the rate is a TNA, not whether 30% comes as 30 or 0.30."""
    return quoted / 100 if quoted > 1 else quoted


def gain(amount: float, rate: float, days: int) -> float:
    return amount * rate * days / 365


def _best_rate(term_id: int) -> float | None:
    """A lender placing at market takes what the best borrower asks."""
    quotes = sorted(get_iol().repo_quotes(term_id), key=lambda q: q.position)
    return next((annual_rate(q.ask.rate) for q in quotes if q.ask.rate > 0), None)


def _shortest_term():
    return min(get_iol().repo_terms(), key=lambda t: t.term_days)


def refresh() -> None:
    """Keep the last rate seen, for when the market is closed."""
    if not market_hours.is_open():
        return
    rate = _best_rate(_shortest_term().term_id)
    if rate is not None:
        now = datetime.now(timezone.utc).isoformat()
        get_db().table("api_cache").upsert({"key": CACHE_KEY, "value": {"rate": rate, "at": now}, "created_at": now}).execute()


def _last_rate() -> tuple[float, datetime] | None:
    rows = get_db().table("api_cache").select("value").eq("key", CACHE_KEY).execute().data
    if not rows:
        return None
    value = rows[0]["value"]  # type: ignore[index]
    at = datetime.fromisoformat(str(value["at"]))  # type: ignore[index, call-overload]
    return (float(value["rate"]), at) if datetime.now(timezone.utc) - at < MAX_RATE_AGE else None  # type: ignore[index, call-overload, arg-type]


def suggest(idle: float) -> CaucionSuggestion | None:
    """None when the money is below IOL's minimum, there's no recent rate, or costs eat the gain."""
    term = _shortest_term()
    if idle < term.min_amount:
        return None
    rate, live = _best_rate(term.term_id), True
    at = datetime.now(timezone.utc)
    if rate is None:
        last = _last_rate()
        if last is None:
            return None
        rate, at = last
        live = False
    costs = None
    try:
        costs = sum(f.amount + f.vat_amount for f in get_iol().estimate_repo(idle, term.term_id))
    except Exception:
        log.warning("no cost estimate for a caución")
    earned = gain(idle, rate, term.term_days)
    if earned - (costs or 0.0) <= 0:
        return None
    return CaucionSuggestion(
        amount=round(idle, 2), term_days=term.term_days, due_date=term.due_date.date(), rate=rate,
        rate_at=at, live=live, gain=round(earned, 2), costs=round(costs, 2) if costs is not None else None,
    )
