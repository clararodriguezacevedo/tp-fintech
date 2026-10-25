"""Dividends and bond coupons: the day the price drops because a payment detaches.

Dividends come from Nasdaq's ex-dividend calendar (free, no key), which covers every US share
behind our CEDEARs and the ADRs of Argentine companies; an ADR's ex-date is taken as the local
share's too. The yield (amount over the previous US close) is the same for the ADR, the local
share and the CEDEAR, whatever their ratios. When IOL has no US price for the ADR, the yield
is left unknown and the event is handled like a coupon.

The Bonares and Globales from the 2020 restructuring pay on January 9 and July 9. The amount
varies per payment, so coupons are stored without one; the ex-date is taken as the business
day before payment.
"""

import logging
from datetime import date, datetime, timedelta, timezone

import httpx
from pydantic import BaseModel

from app import prices
from app.analysis.tagger import UNIVERSE
from app.db import get_db

log = logging.getLogger(__name__)

NASDAQ = "https://api.nasdaq.com/api/calendar/dividends"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

# US symbol -> our ticker, where they differ. ADRs of Argentine companies with the same symbol
# as the local share (GGAL, BMA, SUPV, BBAR, CEPU, LOMA, EDN) need no entry.
US_TO_LOCAL = {"YPF": "YPFD", "PAM": "PAMP", "TGS": "TGSU2", "TEO": "TECO2", "CRESY": "CRES", "BRK.B": "BRKB"}
LOCAL_TO_US = {v: k for k, v in US_TO_LOCAL.items()}
COUPON_BONDS = {"AL29", "GD29", "AL30", "GD30", "AL35", "GD35", "AE38", "GD38", "AL41", "GD41", "GD46"}
COUPON_DAYS = ((1, 9), (7, 9))


class CorporateEvent(BaseModel):
    ticker: str
    ex_date: date
    kind: str  # "dividend" or "coupon"
    amount: float | None = None
    yield_: float | None = None
    source: str


def _prev_business_day(day: date) -> date:
    day -= timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def coupon_ex_dates(year: int) -> list[date]:
    out = []
    for month, dom in COUPON_DAYS:
        pay = date(year, month, dom)
        while pay.weekday() >= 5:  # paid the next business day when it falls on a weekend
            pay += timedelta(days=1)
        out.append(_prev_business_day(pay))
    return out


def _local_ticker(us_symbol: str, tradable: set[str]) -> str | None:
    symbol = us_symbol.replace("/", ".").upper()
    local = US_TO_LOCAL.get(symbol, symbol)
    return local if local in tradable else None


def _yield(ticker: str, ex_date: date, amount: float) -> float | None:
    """Dividend over the US close before the ex-date."""
    try:
        days = (date.today() - ex_date).days + 15
        bars = prices.daily_bars(LOCAL_TO_US.get(ticker, ticker), days=max(days, 15), market="US")
        before = [b for b in bars if b.day < ex_date and b.close > 0]
        return amount / before[-1].close if before else None
    except Exception:
        log.warning("no US price for %s to compute its dividend yield", ticker)
        return None


def fetch_dividends(day: date, tradable: set[str], client: httpx.Client) -> list[CorporateEvent]:
    r = client.get(NASDAQ, params={"date": day.isoformat()}, headers=HEADERS)
    r.raise_for_status()
    rows = ((r.json().get("data") or {}).get("calendar") or {}).get("rows") or []
    out = []
    for row in rows:
        ticker = _local_ticker(str(row.get("symbol", "")), tradable)
        if not ticker or not row.get("dividend_Rate"):
            continue
        ex = datetime.strptime(row["dividend_Ex_Date"], "%m/%d/%Y").date()
        amount = float(row["dividend_Rate"])
        out.append(CorporateEvent(
            ticker=ticker, ex_date=ex, kind="dividend", amount=amount,
            yield_=_yield(ticker, ex, amount), source="nasdaq",
        ))
    return out


def refresh(tradable: set[str], today: date | None = None, back: int = 5, ahead: int = 7) -> int:
    """Store dividends from `back` days ago to `ahead` days out, plus this year's and next
    year's coupons. Returns how many events were saved."""
    today = today or date.today()
    events: list[CorporateEvent] = []
    with httpx.Client(timeout=20) as client:
        for offset in range(-back, ahead + 1):
            day = today + timedelta(days=offset)
            if day.weekday() >= 5:
                continue
            try:
                events += fetch_dividends(day, tradable, client)
            except Exception:
                log.warning("no dividend calendar for %s", day)
    for year in (today.year, today.year + 1):
        for ex in coupon_ex_dates(year):
            events += [
                CorporateEvent(ticker=t, ex_date=ex, kind="coupon", source="calendario")
                for t in sorted(COUPON_BONDS & tradable)
            ]
    if events:
        now = datetime.now(timezone.utc).isoformat()
        get_db().table("corporate_events").upsert([{
            "ticker": e.ticker, "ex_date": e.ex_date.isoformat(), "kind": e.kind, "amount": e.amount,
            "yield": e.yield_, "source": e.source, "fetched_at": now,
        } for e in events], on_conflict="ticker,ex_date,kind").execute()
    log.info("saved %d corporate events", len(events))
    return len(events)


def tradable_tickers(holdings: set[str]) -> set[str]:
    return {t for group in UNIVERSE.values() for t in group} | holdings


def events_between(start: date, end: date) -> dict[tuple[str, date], CorporateEvent]:
    rows = get_db().table("corporate_events").select("*").gte("ex_date", start.isoformat()) \
        .lte("ex_date", end.isoformat()).execute().data
    out: dict[tuple[str, date], CorporateEvent] = {}
    for r in rows:
        e = CorporateEvent.model_validate(r | {"yield_": r.get("yield")})  # type: ignore[operator]
        out[(e.ticker, e.ex_date)] = e
    return out


def upcoming(after: date, days: int = 4) -> dict[str, CorporateEvent]:
    """The next event per ticker from `after` (exclusive) to `days` days later."""
    out: dict[str, CorporateEvent] = {}
    for (ticker, _), e in sorted(events_between(after + timedelta(days=1), after + timedelta(days=days)).items(),
                                 key=lambda kv: kv[0][1]):
        out.setdefault(ticker, e)
    return out

