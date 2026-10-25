"""Daily candles, cached in Supabase (daily_bars).

IOL's unadjusted history is slow (several rows per day per ticker), and on Vercel memory doesn't
survive between requests. So closed days are stored once and only the missing tail is asked to
IOL. Today's candle is never stored before the close, since it is still changing.
"""

import logging
from datetime import date, datetime, time, timedelta

from app.analysis import market_hours
from app.brokers.iol import get_iol
from app.db import get_db, rows_as
from app.models.iol import DailyBar

log = logging.getLogger(__name__)


# US markets close at 17:00 or 18:00 Argentina time depending on US daylight saving; waiting
# until 18:00 means a still-open US session is never stored as a closed day.
US_CLOSE = time(18, 0)


def last_closed_day(now: datetime | None = None, close: time = market_hours.CLOSE) -> date:
    """The most recent weekday whose session has already closed (holidays not handled)."""
    now = (now or market_hours.now_art()).astimezone(market_hours.ART)
    day = now.date()
    if now.weekday() >= 5 or now.time() < close:
        day -= timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def _stored(ticker: str, start: date) -> list[DailyBar]:
    return rows_as(
        DailyBar,
        get_db().table("daily_bars").select("day,open,high,low,close,volume").eq("ticker", ticker)
        .gte("day", start.isoformat()).order("day").execute().data,
    )


SPLIT_MIN_RATIO = 1.8  # an overnight jump this big, close to a whole ratio, is a split
SPLIT_TOLERANCE = 0.06


def _split_ratio(prev_close: float, open_: float) -> float | None:
    """10.0 for a 10:1 split (or 0.1 for a 1:10 reverse split), None for a normal gap."""
    if prev_close <= 0 or open_ <= 0:
        return None
    r = prev_close / open_
    big = r if r >= 1 else 1 / r
    if big < SPLIT_MIN_RATIO or abs(big - round(big)) > SPLIT_TOLERANCE * big:
        return None
    return round(big) if r >= 1 else 1 / round(big)


def adjust_splits(bars: list[DailyBar]) -> list[DailyBar]:
    """Scale candles before a split so prices compare across it. IOL's history is unadjusted
    (YPFD went from 83.000 to 8.105 overnight with its 10:1 split in August 2026)."""
    out = list(bars)
    factor = 1.0
    for i in range(len(out) - 1, 0, -1):
        ratio = _split_ratio(bars[i - 1].close, bars[i].open)
        if ratio:
            factor /= ratio
        if factor != 1.0:
            b = bars[i - 1]
            out[i - 1] = b.model_copy(update={
                "open": b.open * factor, "high": b.high * factor, "low": b.low * factor,
                "close": b.close * factor, "volume": b.volume / factor if b.volume else b.volume,
            })
    return out


def daily_bars(
    ticker: str, days: int = 45, now: datetime | None = None, market: str = "BCBA",
    adjust: bool = True,
) -> list[DailyBar]:
    """Closed daily candles for the last `days` calendar days, oldest first, adjusted for
    splits unless adjust=False.

    market="US" gives the US listing (stored as "US:TICKER")."""
    bars = _daily_bars(ticker, days, now, market)
    return adjust_splits(bars) if adjust else bars


def _daily_bars(ticker: str, days: int, now: datetime | None, market: str) -> list[DailyBar]:
    symbol = ticker.upper()
    ticker = symbol if market == "BCBA" else f"{market}:{symbol}"
    start = date.today() - timedelta(days=days)
    last_closed = last_closed_day(now, market_hours.CLOSE if market == "BCBA" else US_CLOSE)
    bars = _stored(ticker, start)
    # Backfill when asked for more history than is cached (e.g. a backtest).
    if bars and bars[0].day > start + timedelta(days=7):
        try:
            older = [
                b for b in get_iol().daily_history(symbol, start, bars[0].day - timedelta(days=1), market)
                if start <= b.day < bars[0].day
            ]
        except Exception:
            log.warning("IOL history unavailable for %s; no backfill", ticker)
            older = []
        if older:
            get_db().table("daily_bars").upsert(
                [{"ticker": ticker, **b.model_dump(mode="json")} for b in older],
                on_conflict="ticker,day",
            ).execute()
            bars = older + bars
    if bars and bars[-1].day >= last_closed:
        return bars

    fetch_from = bars[-1].day + timedelta(days=1) if bars else start
    try:
        history = get_iol().daily_history(symbol, fetch_from, last_closed + timedelta(days=1), market)
    except Exception:
        if not bars:
            raise
        # IOL is down now and then (often at night); what's cached is still useful.
        log.warning("IOL history unavailable for %s; using cached bars", ticker)
        return bars
    fetched = [b for b in history if fetch_from <= b.day <= last_closed]
    if fetched:
        get_db().table("daily_bars").upsert(
            [{"ticker": ticker, **b.model_dump(mode="json")} for b in fetched],
            on_conflict="ticker,day",
        ).execute()
    return bars + fetched


def bar_on(ticker: str, day: date) -> DailyBar | None:
    """The candle of one closed day as it traded (not split-adjusted), from the cache or IOL."""
    for bar in daily_bars(ticker, days=max(7, (date.today() - day).days + 7), adjust=False):
        if bar.day == day:
            return bar
    return None


def close_on(ticker: str, day: date) -> float | None:
    bar = bar_on(ticker, day)
    return bar.close if bar else None
