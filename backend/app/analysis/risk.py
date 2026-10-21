"""Stop loss, take profit and position size from each ticker's volatility."""

from dataclasses import dataclass


def atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float:
    """Average True Range over the last `period` days. Lists are oldest first."""
    if len(closes) < period + 1:
        raise ValueError(f"need at least {period + 1} days of prices")
    true_ranges = [
        max(h - l, abs(h - prev_close), abs(l - prev_close))
        for h, l, prev_close in zip(highs[1:], lows[1:], closes[:-1])
    ]
    return sum(true_ranges[-period:]) / period


@dataclass
class TradePlan:
    entry: float
    stop_loss: float
    take_profit: float
    quantity: int
    max_loss: float


def plan_buy(
    entry: float,
    atr_value: float,
    portfolio_value: float,
    risk_per_trade: float,
    cash_available: float,
    stop_atr: float = 2.0,
    reward_ratio: float = 2.0,
) -> TradePlan:
    """Stop at `stop_atr` ATRs below entry, target at `reward_ratio` times that distance.

    Quantity is sized so hitting the stop loses `risk_per_trade` of the portfolio, capped by
    the cash available.
    """
    stop_distance = stop_atr * atr_value
    risk_budget = portfolio_value * risk_per_trade
    quantity = int(min(risk_budget / stop_distance, cash_available / entry))
    return TradePlan(
        entry=entry,
        stop_loss=round(entry - stop_distance, 2),
        take_profit=round(entry + reward_ratio * stop_distance, 2),
        quantity=quantity,
        max_loss=round(quantity * stop_distance, 2),
    )
