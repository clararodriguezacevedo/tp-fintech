"""The account's value, defined once and used everywhere.

  value = positions valued in pesos + peso cash + dollar cash at the MEP rate

That is how IOL values the account in its daily history (checked on 2026-10-27: yesterday's
equity minus positions at yesterday's prices, peso cash and dollar cash at the MEP rate left
$ 294 of sale fees), so today's value and every past day compare one to one. Selling moves
value from positions to cash; only deposits and withdrawals change it without a gain or a loss.
"""

import logging
import time
from datetime import date, datetime, timedelta

from pydantic import BaseModel

from app.analysis import market_hours
from app.brokers.iol import get_iol
from app.portfolio import Snapshot, current_holdings, latest_snapshot
from app.schemas import Transfer

log = logging.getLogger(__name__)

MEP_MAX_AGE = 3600.0  # seconds; IOL publishes one rate per day
_mep: tuple[float, float] | None = None  # (rate, fetched at)


class AccountValue(BaseModel):
    captured_at: datetime
    positions: float  # positions valued in pesos
    cash_ars: float
    cash_usd: float
    mep: float | None  # pesos per dollar, from IOL's latest daily history
    cash_usd_ars: float  # cash_usd at the MEP rate (0 if the rate is unknown)
    total: float


def mep_rate() -> float | None:
    """The latest MEP rate in IOL's account history (cached for an hour)."""
    global _mep
    if _mep and time.time() - _mep[1] < MEP_MAX_AGE:
        return _mep[0]
    today = market_hours.now_art().date()
    try:
        days = get_iol().account_history(today - timedelta(days=7), today - timedelta(days=1)).history
        rate = next((d.exchange_rate.mep for d in reversed(days) if d.exchange_rate.mep > 0), None)
    except Exception:
        log.warning("no MEP rate from IOL")
        return _mep[0] if _mep else None
    if rate:
        _mep = (rate, time.time())
    return rate


def _balances() -> tuple[float, float]:
    b = get_iol().balances()
    return b.ars.totals.total, b.usd.totals.total


def value_of(snap: Snapshot) -> AccountValue:
    cash_ars, cash_usd = snap.cash_ars, snap.cash_usd
    if cash_ars is None:
        # A snapshot from before cash was stored: ask IOL now.
        try:
            cash_ars, cash_usd = _balances()
        except Exception:
            log.warning("no cash for the account value")
    cash_ars, cash_usd = cash_ars or 0.0, cash_usd or 0.0
    positions = sum(h.value for h in snap.holdings if h.currency == "ARS")
    mep = mep_rate() if cash_usd else None
    usd_ars = cash_usd * mep if mep else 0.0
    return AccountValue(
        captured_at=snap.captured_at, positions=positions, cash_ars=cash_ars, cash_usd=cash_usd,
        mep=mep if mep is not None else mep_rate(), cash_usd_ars=usd_ars,
        total=positions + cash_ars + usd_ars,
    )


def current() -> AccountValue:
    """The account now: fresh holdings while the market is open, the closing ones after."""
    return value_of(current_holdings())


def latest_cash_total() -> float:
    """All cash in pesos (dollars at the MEP rate) as of the latest snapshot."""
    snap = latest_snapshot()
    if snap is None:
        return 0.0
    v = value_of(snap)
    return v.cash_ars + v.cash_usd_ars


def daily(start: date, end: date) -> dict[date, float]:
    """IOL's closing value of the account per day, start to end (end must be before today)."""
    history = get_iol().account_history(start, end).history
    return {d.date: d.equity.ars for d in history if d.equity.ars > 0}


def transfers(start: date, end: date) -> list[Transfer]:
    """Peso deposits (+) and withdrawals (-), newest first."""
    movements = get_iol().movements(start, end)
    return [
        Transfer(day=m.trade_date.date(), amount=m.net_amount)
        for m in sorted(movements, key=lambda m: m.trade_date, reverse=True)
        if m.activity_type in ("Deposit", "Withdrawal") and m.currency == "ARS"
    ]
