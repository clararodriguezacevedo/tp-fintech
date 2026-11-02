"""How much of a CEDEAR's move is the dollar.

A CEDEAR's price in pesos follows its share in the US and the dollar implicit in CEDEARs. One
CEDEAR alone can't tell them apart: BYMA closes before New York, so its own difference is mostly
timing (on 2026-10-29 MSFT's was +2.0 and VIST's -1.3, with a median of +0.1). So every CEDEAR gets
the same dollar: the median difference across a basket of liquid ones. The rest of its move is the
share, which makes both parts add up to the move shown on the page.
"""

import logging
import statistics
from datetime import date, datetime, timedelta, timezone

from pydantic import BaseModel

from app import prices
from app.analysis import market_hours
from app.brokers.iol import get_iol
from app.db import get_db
from app.models.iol import Quote

log = logging.getLogger(__name__)

BASKET = ("SPY", "QQQ", "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "KO", "XOM")
MIN_PAIRS = 5  # fewer than this and a single CEDEAR could set the median
CACHE_KEY = "cedear_dollar"
CACHE_TTL = timedelta(minutes=10)  # the basket takes about 20 IOL calls


class DollarMove(BaseModel):
    day: date
    change: float
    live: bool  # today's session, the same basis as "Hoy"; otherwise the last two closes
    pairs: int


def _change(q: Quote) -> float | None:
    prev = q.prices.previous_close
    return q.price / prev - 1 if prev and q.price else None


def _from_quotes(today: date) -> DollarMove | None:
    """None until both markets have traded today (New York opens after BYMA)."""
    diffs = []
    for ticker in BASKET:
        try:
            local, us = get_iol().quote(ticker), get_iol().quote(ticker, "US")
        except Exception:
            log.warning("no quotes for %s", ticker)
            continue
        a, b = _change(local), _change(us)
        if a is not None and b is not None and local.last_updated.date() == today == us.last_updated.date():
            diffs.append(a - b)
    if len(diffs) < MIN_PAIRS:
        return None
    return DollarMove(day=today, change=statistics.median(diffs), live=True, pairs=len(diffs))


def _from_closes() -> DollarMove | None:
    """The last day both markets closed, against the day before it."""
    by_day: dict[date, list[float]] = {}
    for ticker in BASKET:
        try:
            local = {b.day: b.close for b in prices.daily_bars(ticker) if b.close > 0}
            us = {b.day: b.close for b in prices.daily_bars(ticker, market="US") if b.close > 0}
        except Exception:
            log.warning("no closes for %s", ticker)
            continue
        days = sorted(set(local) & set(us))
        if len(days) >= 2:
            a, b = days[-2], days[-1]
            by_day.setdefault(b, []).append((local[b] / local[a] - 1) - (us[b] / us[a] - 1))
    if not by_day:
        return None
    day = max(by_day)
    if len(by_day[day]) < MIN_PAIRS:
        return None
    return DollarMove(day=day, change=statistics.median(by_day[day]), live=False, pairs=len(by_day[day]))


def dollar_move() -> DollarMove | None:
    db = get_db()
    rows = db.table("api_cache").select("value,created_at").eq("key", CACHE_KEY).execute().data
    if rows:
        age = datetime.now(timezone.utc) - datetime.fromisoformat(str(rows[0]["created_at"]))  # type: ignore[index]
        if age < CACHE_TTL:
            return DollarMove.model_validate(rows[0]["value"])  # type: ignore[index]
    move = _from_quotes(market_hours.now_art().date()) or _from_closes()
    if move:
        db.table("api_cache").upsert({
            "key": CACHE_KEY, "value": move.model_dump(mode="json"), "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    return move
