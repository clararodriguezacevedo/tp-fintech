"""What a prediction market about the world means for each asset.

Gemini doesn't guess which tickers a market moves: it says which factor the market is about and
whether YES pushes that factor up or down. This table, fixed and readable, says who it reaches.
"""

from dataclasses import dataclass

from app import universe

PREFIX = "F:"


@dataclass(frozen=True)
class Factor:
    label: str
    up: tuple[str, ...] = ()  # rise with the factor
    down: tuple[str, ...] = ()  # fall with the factor


# "@leaders" and "@sovereign" stand for the Merval leaders and the sovereign dollar bonds.
FACTORS = {
    "F:OIL": Factor("Precio del petróleo", up=("XOM", "CVX", "COP", "SHEL", "PBR", "XLE", "USO", "VIST", "YPFD", "PAMP")),
    "F:GOLD": Factor("Precio del oro", up=("GLD", "NEM")),
    "F:BITCOIN": Factor("Precio de bitcoin", up=("IBIT", "COIN", "MSTR")),
    "F:US_STOCKS": Factor("Bolsa de EE.UU.", up=("SPY", "QQQ", "DIA", "IWM")),
    "F:AI_TECH": Factor("Tecnología e IA", up=("QQQ", "XLK", "NVDA", "MSFT", "GOOGL", "AMZN", "META", "AAPL", "TSM", "ASML", "AMD", "AVGO")),
    "F:US_RATES": Factor("Tasas de EE.UU.", down=("SPY", "QQQ", "IWM", "GLD")),
    "F:AR_RISK": Factor("Riesgo argentino", down=("@sovereign", "@leaders")),
}

# A bet on where one of these prices lands still says something about other assets. A bet on a
# stock or an index only repeats its price: if it rose, the bet rose after it.
PRICE_FACTORS = {"F:OIL", "F:GOLD", "F:BITCOIN"}


def is_factor(target: str) -> bool:
    return target.startswith(PREFIX)


def reach(factor: str) -> dict[str, int]:
    """ticker -> +1 if it rises with the factor, -1 if it falls."""
    f = FACTORS.get(factor)
    if f is None:
        return {}
    g = universe.groups()
    groups = {"@leaders": g.leaders, "@sovereign": g.sovereign}
    out: dict[str, int] = {}
    for sign, names in ((1, f.up), (-1, f.down)):
        for name in names:
            for ticker in groups.get(name, {name}):
                out[ticker] = sign
    return out
