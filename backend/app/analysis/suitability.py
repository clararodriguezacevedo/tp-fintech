"""Investor profile (CNV suitability): which assets may be recommended to whom, and how big.

Every asset gets a risk level from its kind and how much its price moves (annualized
volatility of daily returns over the last ~3 months):

  1 bajo    bonds and notes (Títulos Públicos, ONs, letras) moving <= BOND_LOW_VOL a year
  2 medio   other bonds; shares, CEDEARs and ETFs moving <= EQUITY_MID_VOL a year
  3 alto    shares, CEDEARs and ETFs moving more, and anything whose kind or price history is
            unknown (unknown is treated as risky, never as safe)

A profile allows up to a level: conservador 1, moderado 2, arriesgado 3. Nothing above the
profile is ever recommended to buy (it shows as keep, with the reason). Buying one anyway
needs an explicit "I understand it's outside my profile". Sizing also follows the profile.
"""

import math
import statistics
from dataclasses import dataclass
from typing import Literal

from app.models.iol import DailyBar

Profile = Literal["conservador", "moderado", "arriesgado"]
Kind = Literal["bond", "etf", "cedear", "stock", "unknown"]

PROFILES: tuple[Profile, ...] = ("conservador", "moderado", "arriesgado")
MAX_LEVEL: dict[Profile, int] = {"conservador": 1, "moderado": 2, "arriesgado": 3}
LEVEL_NAME = {1: "bajo", 2: "medio", 3: "alto"}

# Sizing per profile: share of the portfolio a stop-out may lose, and the most one ticker may be.
RISK_PER_TRADE: dict[Profile, float] = {"conservador": 0.005, "moderado": 0.01, "arriesgado": 0.015}
MAX_POSITION: dict[Profile, float] = {"conservador": 0.05, "moderado": 0.10, "arriesgado": 0.15}

BOND_LOW_VOL = 0.12
EQUITY_MID_VOL = 0.30
MIN_BARS = 20

ETFS = {"SPY", "QQQ", "GLD", "XLP", "DIA", "IWM", "EEM", "EWZ", "XLE", "XLF", "XLK", "XLV", "SLV", "VEA", "VWO", "ARKK"}
BOND_TYPES = {"TIT. PUBLICOS", "TITULOSPUBLICOS", "OBLIGACIONES NEGOCIABLES", "OBLIGACIONESNEGOCIABLES", "LETRAS"}


@dataclass
class RiskLevel:
    level: int
    kind: Kind
    volatility: float | None  # annualized, as a fraction


def kind_of(ticker: str, asset_type: str | None) -> Kind:
    t = (asset_type or "").upper().replace(" ", "") if asset_type else ""
    if t and any(t == b.replace(" ", "") for b in BOND_TYPES):
        return "bond"
    if ticker in ETFS:
        return "etf"
    if t == "CEDEARS":
        return "cedear"
    if t == "ACCIONES":
        return "stock"
    return "unknown"


def annual_volatility(bars: list[DailyBar], days: int = 60) -> float | None:
    closes = [b.close for b in bars if b.close > 0][-(days + 1):]
    if len(closes) < MIN_BARS:
        return None
    returns = [math.log(b / a) for a, b in zip(closes, closes[1:])]
    return statistics.pstdev(returns) * math.sqrt(252)


def risk_level(ticker: str, asset_type: str | None, bars: list[DailyBar]) -> RiskLevel:
    kind = kind_of(ticker, asset_type)
    vol = annual_volatility(bars)
    if kind == "bond":
        level = 1 if vol is not None and vol <= BOND_LOW_VOL else 2
    elif kind in ("etf", "cedear", "stock"):
        level = 2 if vol is not None and vol <= EQUITY_MID_VOL else 3
    else:
        level = 3
    return RiskLevel(level=level, kind=kind, volatility=vol)


def allowed(level: int, profile: Profile) -> bool:
    return level <= MAX_LEVEL[profile]
