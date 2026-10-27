"""The user's IOL holdings, snapshotted in Supabase (holdings_snapshots).

Snapshots are stored at most every 30 minutes while BYMA is open (plus one after the close) and
double as the portfolio's value over time. What the user sees is fresher: `current_holdings`
goes back to IOL whenever the latest snapshot is more than a few minutes old.

The cash in the account is stored with each snapshot (cash_snapshots): when a position is sold,
its value moves to cash, so the portfolio is the holdings plus the cash.
"""

import logging
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel

from app.analysis import market_hours
from app.brokers.iol import get_iol
from app.db import get_db

log = logging.getLogger(__name__)

# A new snapshot is stored at most this often while BYMA is open, plus one after the close.
SNAPSHOT_EVERY = timedelta(minutes=30)
# What the user sees may be at most this old while BYMA is open.
DISPLAY_MAX_AGE = timedelta(minutes=5)
# Background jobs (scoring, tagging) tolerate older data.
MAX_AGE = timedelta(hours=2)

# IOL's instrument types, normalized to the names the rest of the app (and stored snapshots) use.
TYPES = {"TIT. PUBLICOS": "TitulosPublicos", "OBLIGACIONES NEGOCIABLES": "ObligacionesNegociables"}
EQUITY_TYPES = {"ACCIONES", "Acciones"}
BOND_TYPES = {"TitulosPublicos", "ObligacionesNegociables"}


class Holding(BaseModel):
    ticker: str
    description: str
    type: str
    currency: str = "ARS"  # what last_price, avg_price, value and gain_amount are quoted in
    quantity: float
    last_price: float
    avg_price: float
    value: float
    gain_pct: float
    gain_amount: float = 0.0
    day_change_pct: float = 0.0


class Snapshot(BaseModel):
    captured_at: datetime
    holdings: list[Holding]
    cash_ars: float | None = None  # pesos in the account (None: unknown for this snapshot)
    cash_usd: float | None = None

    @property
    def total_ars(self) -> float:
        """Holdings valued in pesos plus the peso cash."""
        return sum(h.value for h in self.holdings if h.currency == "ARS") + (self.cash_ars or 0.0)


def _fetch_from_iol() -> list[Holding]:
    return [
        Holding(
            ticker=p.instrument.symbol.upper(),
            description=p.instrument.name,
            type=TYPES.get(p.instrument.type, p.instrument.type),
            currency="USD" if p.instrument.currency == "USD" else "ARS",
            quantity=p.quantity,
            last_price=p.market_value.current_price,
            avg_price=p.cost_basis.average_entry_price,
            value=p.value,
            gain_pct=p.profit_loss.unrealized_pl_percent,
            gain_amount=p.gain_amount,
            day_change_pct=p.market_value.price_change_percent,
        )
        for p in get_iol().positions().positions
    ]


def _fetch_cash() -> tuple[float | None, float | None]:
    """(pesos, dollars) in the account, settled or not; (None, None) if IOL can't answer."""
    try:
        b = get_iol().balances()
        return b.ars.totals.total, b.usd.totals.total
    except Exception:
        log.warning("no balances from IOL; snapshot without cash")
        return None, None


def _fetch_snapshot(now: datetime) -> Snapshot:
    cash_ars, cash_usd = _fetch_cash()
    return Snapshot(captured_at=now, holdings=_fetch_from_iol(), cash_ars=cash_ars, cash_usd=cash_usd)


def cash_at(captured_at: datetime | str) -> tuple[float | None, float | None]:
    when = captured_at if isinstance(captured_at, str) else captured_at.isoformat()
    rows = get_db().table("cash_snapshots").select("ars,usd").eq("captured_at", when).execute().data
    if not rows:
        return None, None
    return float(rows[0]["ars"]), float(rows[0]["usd"])  # type: ignore[index, arg-type]


def latest_snapshot() -> Snapshot | None:
    db = get_db()
    head = (
        db.table("holdings_snapshots").select("captured_at").order("captured_at", desc=True)
        .limit(1).execute().data
    )
    if not head:
        return None
    captured_at = head[0]["captured_at"]  # type: ignore[index]
    rows = db.table("holdings_snapshots").select("*").eq("captured_at", captured_at).execute().data
    holdings = [Holding.model_validate(r) for r in rows]
    cash_ars, cash_usd = cash_at(str(captured_at))
    return Snapshot(
        captured_at=datetime.fromisoformat(str(captured_at)), holdings=holdings,
        cash_ars=cash_ars, cash_usd=cash_usd,
    )


def _last_close_time(now: datetime) -> datetime:
    from app.prices import last_closed_day  # avoid an import cycle

    day = last_closed_day(now)
    return datetime.combine(day, market_hours.CLOSE, tzinfo=market_hours.ART)


def _due(latest: Snapshot | None, now: datetime) -> bool:
    if latest is None:
        return True
    if market_hours.is_open(now.astimezone(market_hours.ART)):
        return now - latest.captured_at >= SNAPSHOT_EVERY
    return latest.captured_at < _last_close_time(now)


def _save(snap: Snapshot) -> None:
    if snap.holdings:
        get_db().table("holdings_snapshots").insert(
            [{"captured_at": snap.captured_at.isoformat(), **h.model_dump()} for h in snap.holdings]
        ).execute()
        log.info("saved holdings snapshot with %d positions", len(snap.holdings))
    if snap.cash_ars is not None:
        get_db().table("cash_snapshots").upsert({
            "captured_at": snap.captured_at.isoformat(), "ars": snap.cash_ars, "usd": snap.cash_usd or 0.0,
        }).execute()


def refresh_holdings(force: bool = False) -> list[Holding]:
    """Fetch from IOL and save a snapshot if one is due. Called by the collection cycle."""
    now = datetime.now(timezone.utc)
    latest = latest_snapshot()
    if not force and not _due(latest, now) and latest is not None:
        return latest.holdings
    snap = _fetch_snapshot(now)
    _save(snap)
    return snap.holdings


def current_holdings() -> Snapshot:
    """Holdings for display: never more than a few minutes old while the market is open, and
    taken after the close once it's closed. Falls back to the last snapshot if IOL is down."""
    now = datetime.now(timezone.utc)
    latest = latest_snapshot()
    if latest is not None:
        if market_hours.is_open(now.astimezone(market_hours.ART)):
            fresh = now - latest.captured_at <= DISPLAY_MAX_AGE
        else:
            fresh = latest.captured_at >= _last_close_time(now)
        if fresh:
            return latest
    try:
        snap = _fetch_snapshot(now)
    except Exception:
        if latest is None:
            raise
        log.exception("IOL unavailable; showing the last snapshot")
        return latest
    if _due(latest, now):
        _save(snap)
    return snap


def latest_cash() -> float:
    """Peso cash as of the latest snapshot, or live from IOL; 0 if neither is available."""
    latest = latest_snapshot()
    if latest and latest.cash_ars is not None:
        return latest.cash_ars
    return _fetch_cash()[0] or 0.0


def get_holdings() -> list[Holding]:
    """Current holdings: the latest snapshot, or IOL directly if it's missing or too old."""
    latest = latest_snapshot()
    if latest is None or datetime.now(timezone.utc) - latest.captured_at > MAX_AGE:
        return refresh_holdings(force=True)
    return latest.holdings


def value_history(days: int = 90) -> list[tuple[datetime, float]]:
    """Total portfolio value (holdings plus peso cash, where known) per snapshot, oldest first."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    totals: dict[str, float] = {}
    page = 0
    while True:
        rows = (
            get_db().table("holdings_snapshots").select("captured_at,value")
            .gte("captured_at", since).order("captured_at")
            .range(page * 1000, page * 1000 + 999).execute().data
        )
        for r in rows:
            key = str(r["captured_at"])  # type: ignore[index]
            totals[key] = totals.get(key, 0.0) + float(r["value"])  # type: ignore[index, arg-type]
        if len(rows) < 1000:
            break
        page += 1
    cash = {
        datetime.fromisoformat(str(r["captured_at"])): float(r["ars"])  # type: ignore[index, arg-type]
        for r in get_db().table("cash_snapshots").select("captured_at,ars").gte("captured_at", since).execute().data
    }
    return [(t, v + cash.get(t, 0.0)) for t, v in ((datetime.fromisoformat(k), v) for k, v in totals.items())]
