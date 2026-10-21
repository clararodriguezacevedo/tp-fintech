"""The user's current IOL holdings, cached so every job doesn't hit IOL again."""

import time

from pydantic import BaseModel

from app.brokers.iol import get_iol

CACHE_SECONDS = 600

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


_cache: tuple[float, list[Holding]] | None = None


def get_holdings(refresh: bool = False) -> list[Holding]:
    global _cache
    if _cache and not refresh and time.time() - _cache[0] < CACHE_SECONDS:
        return _cache[1]
    holdings = [
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
    _cache = (time.time(), holdings)
    return holdings
