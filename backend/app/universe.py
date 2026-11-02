"""Every asset IOL offers in our categories: acciones, CEDEARs (ETFs come inside them) and bonos.

Read from IOL's panels and stored in `assets`, refreshed once a day. Only the peso species with a
price: the dollar species (AL30D, VISTD) are the same asset, and a symbol without a price isn't
trading. Gemini can tag any of them, but only those with evidence, in the portfolio or that
broad news applies to get scored (app.analysis.scoring). Broad MERVAL news applies to the Merval
leaders and broad BONOS news to the sovereign dollar bonds, which also make up the market context.

The panels' prices match IOL's quote one by one (checked on KO, NU and ASML), so one call per
category replaces a call per ticker.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel

from app.analysis.tagger import UNIVERSE as BASE
from app.brokers.iol import get_iol
from app.db import get_db

log = logging.getLogger(__name__)

TERM = "T1"
# category: (IOL's asset type, its panels, the type name stored for suitability)
CATEGORIES = {
    "acciones": ("acciones", ("argaccionespanelgeneral", "argaccionessubastas"), "ACCIONES"),
    "cedears": ("cedears", ("argcedearstodos",), "CEDEARS"),
    "bonos": ("bonos", ("argbonostodos",), "TIT. PUBLICOS"),
}
LEADERS = ("acciones", "argaccionesmerval")
SOVEREIGN = ("bonos", "argbonossoberanosendolares")
REFRESH_EVERY = timedelta(hours=24)
CACHE_SECONDS = 600.0
PAGE = 1000


class Asset(BaseModel):
    ticker: str
    name: str
    category: str
    leader: bool = False
    sovereign: bool = False
    last_price: float | None = None


@dataclass
class Groups:
    stocks: set[str] = field(default_factory=set)
    bonds: set[str] = field(default_factory=set)
    cedears: set[str] = field(default_factory=set)
    leaders: set[str] = field(default_factory=set)
    sovereign: set[str] = field(default_factory=set)
    names: dict[str, str] = field(default_factory=dict)


_cache: tuple[float, Groups] | None = None


def _panel(asset_type: str, panel: str) -> list[dict]:
    rows = get_iol()._request(
        "GET", "/broker/market-data/screener",
        params={"country": "AR", "asset_type": asset_type, "panel": panel, "term": TERM},
    )
    return rows if isinstance(rows, list) else []


def _priced_in_pesos(rows: list[dict]) -> dict[str, dict]:
    return {
        r["instrument"]["symbol"].upper(): r for r in rows
        if r["instrument"].get("currency") == "ARS" and (r["quotes"].get("last") or 0) > 0
    }


def clean_name(name: str) -> str:
    return name.removeprefix("Cedear ").strip()


def build_assets(panels: dict[str, list[dict]], leaders: set[str], sovereign: set[str]) -> list[Asset]:
    """panels: category -> screener rows. A ticker in two categories keeps the first."""
    assets: dict[str, Asset] = {}
    for category, rows in panels.items():
        for ticker, r in _priced_in_pesos(rows).items():
            assets.setdefault(ticker, Asset(
                ticker=ticker, name=clean_name(r["instrument"].get("name") or ticker), category=category,
                leader=ticker in leaders, sovereign=ticker in sovereign, last_price=r["quotes"]["last"],
            ))
    return list(assets.values())


def fetch_assets() -> list[Asset]:
    panels = {
        category: [r for panel in panel_ids for r in _panel(asset_type, panel)]
        for category, (asset_type, panel_ids, _) in CATEGORIES.items()
    }
    return build_assets(panels, set(_priced_in_pesos(_panel(*LEADERS))), set(_priced_in_pesos(_panel(*SOVEREIGN))))


def refresh() -> int:
    """Store IOL's current assets and their kinds. Returns how many."""
    global _cache
    assets = fetch_assets()
    if not assets:
        raise RuntimeError("IOL returned no assets")
    now = datetime.now(timezone.utc).isoformat()
    db = get_db()
    # A ticker that left the panels stops being leader or sovereign; load() ignores it once stale.
    for i in range(0, len(assets), 500):
        chunk = assets[i : i + 500]
        db.table("assets").upsert([a.model_dump() | {"updated_at": now} for a in chunk]).execute()
        db.table("asset_types").upsert([
            {"ticker": a.ticker, "asset_type": CATEGORIES[a.category][2], "fetched_at": now} for a in chunk
        ]).execute()
    _cache = None
    log.info("universe: %d assets", len(assets))
    return len(assets)


def refresh_if_stale() -> None:
    rows = get_db().table("assets").select("updated_at").order("updated_at", desc=True).limit(1).execute().data
    newest = str(rows[0]["updated_at"]) if rows else None  # type: ignore[index]
    if not newest or datetime.now(timezone.utc) - datetime.fromisoformat(newest) > REFRESH_EVERY:
        refresh()


def load() -> list[Asset]:
    """The stored assets seen in the last week, so one failed refresh doesn't lose any."""
    since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    out: list[Asset] = []
    page = 0
    while True:
        rows = (
            get_db().table("assets").select("ticker,name,category,leader,sovereign,last_price")
            .gte("updated_at", since).order("ticker").range(page * PAGE, page * PAGE + PAGE - 1).execute().data
        )
        out += [Asset.model_validate(r) for r in rows]
        if len(rows) < PAGE:
            return out
        page += 1


def groups() -> Groups:
    """The universe by group, cached for a few minutes. The short base list if nothing is stored."""
    global _cache
    if _cache and time.time() - _cache[0] < CACHE_SECONDS:
        return _cache[1]
    try:
        assets = load()
    except Exception:
        log.exception("could not load the universe; using the base list")
        assets = []
    if assets:
        g = Groups(
            stocks={a.ticker for a in assets if a.category == "acciones"},
            bonds={a.ticker for a in assets if a.category == "bonos"},
            cedears={a.ticker for a in assets if a.category == "cedears"},
            leaders={a.ticker for a in assets if a.leader},
            sovereign={a.ticker for a in assets if a.sovereign},
            names={a.ticker: a.name for a in assets},
        )
        _cache = (time.time(), g)
        return g
    return Groups(
        stocks=set(BASE["acciones"]), bonds=set(BASE["bonos"]), cedears=set(BASE["cedears"]),
        leaders=set(BASE["acciones"]), sovereign=set(BASE["bonos"]),
    )


def live_prices() -> dict[str, float]:
    """Price now of every peso asset, with one call per category."""
    out: dict[str, float] = {}
    for asset_type, panel_ids, _ in CATEGORIES.values():
        for panel in panel_ids:
            out |= {t: float(r["quotes"]["last"]) for t, r in _priced_in_pesos(_panel(asset_type, panel)).items()}
    return out
