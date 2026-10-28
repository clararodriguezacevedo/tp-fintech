"""Stop loss, take profit and position size from each ticker's volatility."""

from dataclasses import dataclass, field


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
    limits: dict[str, int] = field(default_factory=dict)
    limited_by: str | None = None
    portfolio_share: float | None = None


MAX_POSITION = 0.10  # no single ticker above this share of the portfolio
OVER_LIMIT_BUY = 0.02  # most a buy can add to a risk group already over the concentration limit
MAX_VOLUME_SHARE = 0.10  # at most this share of the ticker's average daily volume


def plan_buy(
    entry: float,
    atr_value: float,
    portfolio_value: float,
    risk_per_trade: float,
    cash_available: float,
    stop_atr: float = 2.0,
    reward_ratio: float = 2.0,
    held_value: float = 0.0,
    group_value: float | None = None,
    concentration_limit: float = 0.60,
    avg_volume: float | None = None,
    max_position: float = MAX_POSITION,
) -> TradePlan:
    """Stop at `stop_atr` ATRs below entry, target at `reward_ratio` times that distance.

    The quantity is the smallest of what each limit allows:
      risk           hitting the stop loses `risk_per_trade` of the portfolio (so the more
                     volatile the ticker, the smaller the buy)
      cash           the cash available
      position       the ticker, counting what is already held, stays under max_position
                     (by investor profile: 5%, 10% or 15%)
      concentration  its risk group stays under `concentration_limit` of the portfolio; when
                     it is already over, the buy adds at most OVER_LIMIT_BUY
      liquidity      at most MAX_VOLUME_SHARE of the average daily volume, so the order
                     doesn't move the price
    """
    stop_distance = stop_atr * atr_value
    limits = {
        "risk": portfolio_value * risk_per_trade / stop_distance,
        "cash": cash_available / entry,
        "position": max(0.0, max_position * portfolio_value - held_value) / entry,
    }
    if group_value is not None:
        room = concentration_limit * portfolio_value - group_value
        limits["concentration"] = max(room, OVER_LIMIT_BUY * portfolio_value) / entry
    if avg_volume:
        limits["liquidity"] = avg_volume * MAX_VOLUME_SHARE
    whole = {k: max(0, int(v)) for k, v in limits.items()}
    limited_by = min(whole, key=lambda k: whole[k])
    quantity = whole[limited_by]
    return TradePlan(
        entry=entry,
        stop_loss=round(entry - stop_distance, 2),
        take_profit=round(entry + reward_ratio * stop_distance, 2),
        quantity=quantity,
        max_loss=round(quantity * stop_distance, 2),
        limits=whole,
        limited_by=limited_by,
        portfolio_share=round(quantity * entry / portfolio_value, 4) if portfolio_value else None,
    )
