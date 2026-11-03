"""Checks every day that the site's account value matches IOL's own.

After each trading day IOL publishes its closing value of the account. The site's value at that
close (the last snapshot of the day after the market closed) has to match it. Real days since
cash is stored differ by at most 0.10%, from price timing; a counting error is far larger (unsettled
buys counted twice were 22%). Weekends are skipped: on 2026-11-01 IOL's value left the cash out.

A mismatch sends an e-mail.
"""

import logging
from datetime import date, datetime, timedelta, timezone

from pydantic import BaseModel

from app import alerts
from app.analysis import market_hours
from app.brokers.iol import get_iol
from app.db import get_db

log = logging.getLogger(__name__)

TOLERANCE = 0.003  # share of the account
CACHE_KEY = "account_check"


class AccountCheck(BaseModel):
    day: date
    site: float
    iol: float
    diff: float  # site - iol, after transfers made once the snapshot was taken
    ok: bool


def compare(day: date, site: float, iol: float, transfers_after: float = 0.0) -> AccountCheck:
    """transfers_after: deposits (+) and withdrawals (-) between the snapshot and IOL's close."""
    diff = site + transfers_after - iol
    return AccountCheck(day=day, site=round(site, 2), iol=round(iol, 2), diff=round(diff, 2), ok=abs(diff) <= TOLERANCE * abs(iol))


def last_trading_day(today: date) -> date:
    day = today - timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def latest() -> AccountCheck | None:
    rows = get_db().table("api_cache").select("value").eq("key", CACHE_KEY).execute().data
    return AccountCheck.model_validate(rows[0]["value"]) if rows else None  # type: ignore[index, arg-type]


def _site_value_at_close(day: date, mep: float) -> tuple[datetime, float] | None:
    db = get_db()
    since = datetime.combine(day, market_hours.CLOSE, tzinfo=market_hours.ART)
    until = datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=market_hours.ART)
    cash = (
        db.table("cash_snapshots").select("captured_at,ars,usd").gte("captured_at", since.isoformat())
        .lt("captured_at", until.isoformat()).order("captured_at", desc=True).limit(1).execute().data
    )
    if not cash:
        return None
    row = cash[0]
    holdings = db.table("holdings_snapshots").select("value,currency").eq("captured_at", row["captured_at"]).execute().data  # type: ignore[index, arg-type]
    positions = sum(float(h["value"]) for h in holdings if h.get("currency", "ARS") == "ARS")  # type: ignore[union-attr, arg-type]
    total = positions + float(row["ars"]) + float(row["usd"]) * mep  # type: ignore[index, arg-type]
    return datetime.fromisoformat(str(row["captured_at"])), total  # type: ignore[index]


def run() -> AccountCheck | None:
    """Check the last trading day, once. Waits if IOL's value or the snapshot aren't there yet, and
    until today's close: early on, IOL's value for yesterday can be just the positions (at 07:10
    on 2026-11-03 it said 5.436.392 for the 2nd, later 5.917.131)."""
    now = market_hours.now_art()
    if now.time() < market_hours.CLOSE:
        return None
    day = last_trading_day(now.date())
    done = latest()
    if done and done.day >= day:
        return done
    history = get_iol().account_history(day, day).history
    if not history or history[-1].equity.ars <= 0:
        return None
    close = history[-1]
    site = _site_value_at_close(day, close.exchange_rate.mep)
    if site is None:
        return None
    captured, value = site
    after = sum(
        m.net_amount for m in get_iol().movements(day, day)
        if m.activity_type in ("Deposit", "Withdrawal") and m.currency == "ARS"
        and m.trade_date.replace(tzinfo=market_hours.ART) > captured
    )
    check = compare(day, value, close.equity.ars, after)
    get_db().table("api_cache").upsert({
        "key": CACHE_KEY, "value": check.model_dump(mode="json"), "created_at": datetime.now(timezone.utc).isoformat(),
    }).execute()
    if not check.ok:
        log.warning("account check failed: %s", check)
        alerts.send(
            f"check:{day.isoformat()}", "El total de tu cartera no coincide con IOL",
            [f"Al cierre del {day.strftime('%d/%m')}, el sitio da $ {check.site:,.2f} e IOL $ {check.iol:,.2f} "
             f"(diferencia de $ {check.diff:,.2f}).",
             "Hasta revisarlo, confiá en el número de IOL."],
        )
    return check

