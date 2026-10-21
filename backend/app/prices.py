"""Daily candles, cached in Supabase (daily_bars).

IOL's unadjusted history is slow (several rows per day per ticker), and on Vercel memory doesn't
survive between requests. So closed days are stored once and only the missing tail is asked to
IOL. Today's candle is never stored before the close, since it is still changing.
"""

import logging
from datetime import date, datetime, timedelta

from app.analysis import market_hours
from app.brokers.iol import get_iol
from app.db import get_db, rows_as
from app.models.iol import DailyBar

log = logging.getLogger(__name__)


def last_closed_day(now: datetime | None = None) -> date:
    """The most recent weekday whose session has already closed (holidays not handled)."""
    now = (now or market_hours.now_art()).astimezone(market_hours.ART)
    day = now.date()
    if now.weekday() >= 5 or now.time() < market_hours.CLOSE:
        day -= timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def _stored(ticker: str, start: date) -> list[DailyBar]:
    return rows_as(
        DailyBar,
        get_db().table("daily_bars").select("day,open,high,low,close").eq("ticker", ticker)
        .gte("day", start.isoformat()).order("day").execute().data,
    )


def daily_bars(ticker: str, days: int = 45, now: datetime | None = None) -> list[DailyBar]:
    """Closed daily candles for the last `days` calendar days, oldest first."""
    ticker = ticker.upper()
    start = date.today() - timedelta(days=days)
    last_closed = last_closed_day(now)
    bars = _stored(ticker, start)
    if bars and bars[-1].day >= last_closed:
        return bars

    fetch_from = bars[-1].day + timedelta(days=1) if bars else start
    fetched = [
        b for b in get_iol().daily_history(ticker, fetch_from, last_closed + timedelta(days=1))
        if fetch_from <= b.day <= last_closed
    ]
    if fetched:
        get_db().table("daily_bars").upsert(
            [{"ticker": ticker, **b.model_dump(mode="json")} for b in fetched],
            on_conflict="ticker,day",
        ).execute()
    return bars + fetched


def close_on(ticker: str, day: date) -> float | None:
    """Closing price of one day, from the cache or IOL."""
    for bar in daily_bars(ticker, days=max(7, (date.today() - day).days + 7)):
        if bar.day == day:
            return bar.close
    return None
