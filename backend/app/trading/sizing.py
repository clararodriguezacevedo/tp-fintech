"""How much of a ticker to buy, the same for the buy panel and the daily plan.

Sized from the ticker's volatility and capped by cash, the investor profile's maximum per
asset, concentration and liquidity (app.analysis.risk.plan_buy).
"""

from app import prices
from app.analysis import risk, scoring, suitability
from app.analysis.tagger import UNIVERSE
from app.portfolio import BOND_TYPES, EQUITY_TYPES, Holding


def size_buy(
    ticker: str,
    price: float,
    holdings: dict[str, Holding],
    portfolio_value: float,
    cash: float,
    profile: suitability.Profile,
) -> risk.TradePlan:
    """Raises ValueError without enough price history to measure volatility."""
    bars = prices.daily_bars(ticker)
    if len(bars) < 15:
        raise ValueError(f"not enough price history for {ticker}")
    stocks = set(UNIVERSE["acciones"]) | {t for t, h in holdings.items() if h.type in EQUITY_TYPES}
    bonds = set(UNIVERSE["bonos"]) | {t for t, h in holdings.items() if h.type in BOND_TYPES}
    group = scoring.risk_group(ticker, stocks, bonds)
    volumes = [b.volume for b in bars[-20:] if b.volume]
    return risk.plan_buy(
        entry=price,
        atr_value=risk.atr([b.high for b in bars], [b.low for b in bars], [b.close for b in bars]),
        portfolio_value=portfolio_value,
        risk_per_trade=suitability.RISK_PER_TRADE[profile],
        # cash <= 0: size without a cash limit (the daily plan decides how each buy is paid).
        cash_available=cash if cash > 0 else portfolio_value,
        held_value=holdings[ticker].value if ticker in holdings else 0.0,
        group_value=sum(
            h.value for h in holdings.values()
            if h.currency == "ARS" and scoring.risk_group(h.ticker, stocks, bonds) == group
        ),
        concentration_limit=scoring.CONCENTRATION_LIMIT,
        avg_volume=sum(volumes) / len(volumes) if len(volumes) >= 5 else None,
        max_position=suitability.MAX_POSITION[profile],
    )
