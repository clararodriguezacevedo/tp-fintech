"""The user's IOL holdings, snapshotted in Supabase (holdings_snapshots).

The collection cycle refreshes them from IOL; everything else (API, scoring) reads the latest
snapshot, so a page load never waits on IOL and the snapshots double as the portfolio's value
over time.
"""

import logging
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel

from app.analysis import market_hours
from app.brokers.iol import get_iol
from app.db import get_db

log = logging.getLogger(__name__)

# A new snapshot at most this often while BYMA is open, plus one after the close.
SNAPSHOT_EVERY = timedelta(minutes=30)
# Older than this and readers refresh from IOL themselves (e.g. the cycle hasn't run).
MAX_AGE = timedelta(hours=2)

# IOL's titulo.tipo values grouped by what broad tags apply to them.
EQUITY_TYPES = {"ACCIONES", "Acciones"}
BOND_TYPES = {"TitulosPublicos", "ObligacionesNegociables"}


class Holding(BaseModel):
    ticker: str
    description: str
    type: str
    quantity: float
    last_price: float
    avg_price: float
    value: float
    gain_pct: float


class Snapshot(BaseModel):
    captured_at: datetime
    holdings: list[Holding]


def _fetch_from_iol() -> list[Holding]:
    return [
        Holding(
            ticker=a.titulo.simbolo.upper(),
            description=a.titulo.descripcion,
            type=a.titulo.tipo,
            quantity=a.cantidad,
            last_price=a.ultimo_precio,
            avg_price=a.ppc,
            value=a.valorizado,
            gain_pct=a.ganancia_porcentaje,
        )
        for a in get_iol().holdings()
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


def refresh_holdings(force: bool = False) -> list[Holding]:
    """Fetch from IOL and save a snapshot if one is due. Called by the collection cycle."""
    now = datetime.now(timezone.utc)
    latest = latest_snapshot()
    if not force and not _due(latest, now) and latest is not None:
        return latest.holdings
    holdings = _fetch_from_iol()
    if holdings:
        get_db().table("holdings_snapshots").insert(
            [{"captured_at": now.isoformat(), **h.model_dump()} for h in holdings]
        ).execute()
    log.info("saved holdings snapshot with %d positions", len(holdings))
    return holdings


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
