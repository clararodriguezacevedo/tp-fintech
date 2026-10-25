"""Riesgo país and the CCL dollar, from argentinadatos.com (free, no key)."""

import logging
import math
import statistics
from dataclasses import dataclass

import httpx

log = logging.getLogger(__name__)

BASE = "https://api.argentinadatos.com/v1"
HORIZON = 5  # trading days the change is measured over
LOOKBACK = 250  # days of history used to judge what a normal change is


@dataclass
class MacroSignal:
    level: float  # latest value (points for riesgo país, pesos for the CCL)
    change: float  # change over HORIZON days, as a fraction
    signal: float  # tanh of the change in typical changes, in [-1, 1]; + means up


def change_signal(series: list[float], horizon: int = HORIZON, lookback: int = LOOKBACK) -> MacroSignal | None:
    """How unusual the last `horizon`-day change is, versus the last `lookback` days."""
    values = [v for v in series if v > 0]
    if len(values) < horizon + 30:
        return None
    changes = [values[i] / values[i - horizon] - 1 for i in range(max(horizon, len(values) - lookback), len(values))]
    spread = statistics.pstdev(changes)
    change = values[-1] / values[-1 - horizon] - 1
    if spread <= 0:
        return None
    return MacroSignal(level=values[-1], change=change, signal=math.tanh(change / spread / 2))


def _series(client: httpx.Client, path: str, field: str) -> list[float]:
    rows = client.get(f"{BASE}{path}").raise_for_status().json()
    rows = sorted(rows, key=lambda r: r["fecha"])[-(LOOKBACK + HORIZON + 10):]
    return [float(r[field]) for r in rows if r.get(field) is not None]


def fetch() -> dict[str, MacroSignal]:
    """{"riesgo_pais": ..., "ccl": ...}; a source that fails is left out."""
    out: dict[str, MacroSignal] = {}
    with httpx.Client(timeout=20) as client:
        for name, path, field in (
            ("riesgo_pais", "/finanzas/indices/riesgo-pais", "valor"),
            ("ccl", "/cotizaciones/dolares/contadoconliqui", "venta"),
        ):
            try:
                s = change_signal(_series(client, path, field))
                if s:
                    out[name] = s
            except Exception:
                log.warning("no %s data", name)
    return out
