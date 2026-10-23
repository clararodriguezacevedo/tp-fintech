"""The user's IOL holdings, snapshotted in Supabase (holdings_snapshots).

Snapshots are stored at most every 30 minutes while BYMA is open (plus one after the close) and
double as the portfolio's value over time. What the user sees is fresher: `current_holdings`
goes back to IOL whenever the latest snapshot is more than a few minutes old.
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
    return Snapshot(captured_at=datetime.fromisoformat(str(captured_at)), holdings=holdings)


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


def _save(holdings: list[Holding], now: datetime) -> None:
    if holdings:
        get_db().table("holdings_snapshots").insert(
            [{"captured_at": now.isoformat(), **h.model_dump()} for h in holdings]
        ).execute()
        log.info("saved holdings snapshot with %d positions", len(holdings))


def refresh_holdings(force: bool = False) -> list[Holding]:
    """Fetch from IOL and save a snapshot if one is due. Called by the collection cycle."""
    now = datetime.now(timezone.utc)
    latest = latest_snapshot()
    if not force and not _due(latest, now) and latest is not None:
        return latest.holdings
    holdings = _fetch_from_iol()
    _save(holdings, now)
    return holdings


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
        holdings = _fetch_from_iol()
    except Exception:
        if latest is None:
            raise
        log.exception("IOL unavailable; showing the last snapshot")
        return latest
    if _due(latest, now):
        _save(holdings, now)
    return Snapshot(captured_at=now, holdings=holdings)


def get_holdings() -> list[Holding]:
    """Current holdings: the latest snapshot, or IOL directly if it's missing or too old."""
    latest = latest_snapshot()
    if latest is None or datetime.now(timezone.utc) - latest.captured_at > MAX_AGE:
        return refresh_holdings(force=True)
    return latest.holdings


def value_history(days: int = 90) -> list[tuple[datetime, float]]:
    """Total portfolio value per snapshot, oldest first."""
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
    return [(datetime.fromisoformat(k), v) for k, v in totals.items()]
