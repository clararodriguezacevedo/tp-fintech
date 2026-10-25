"""Request and response models of our own API that aren't table rows (those are in
app.models.db). FastAPI publishes all of them in /openapi.json, which the frontend uses to
generate its zod schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.db import Action, Direction, MarketRow, NewsRow, Strength


class Health(BaseModel):
    ok: bool
    market_open: bool
    next_open: datetime
    live_trading: bool
    mode: Literal["paper", "live"]


class Impact(BaseModel):
    ticker: str
    direction: Direction
    strength: Strength


class NewsOut(NewsRow):
    impacts: list[Impact]


class MarketOut(MarketRow):
    impacts: list[Impact]


class JobResult(BaseModel):
    failed: list[str]
    skipped: bool = False


class ProbabilityPoint(BaseModel):
    t: datetime
    p: float = Field(ge=0, le=1)


class AccountSummary(BaseModel):
    total_value: float  # whole account in pesos, as IOL values it
    cash_ars: float
    cash_usd: float


class PortfolioValuePoint(BaseModel):
    t: datetime
    value: float  # pesos
    value_usd_mep: float | None = None  # same value in dollars at that day's MEP rate


class TradePlan(BaseModel):
    entry: float
    stop_loss: float
    take_profit: float
    quantity: int
    max_loss: float
    market_open: bool
    fees: float | None = None  # commission + VAT + market fee IOL estimates for this order
    # The quantity each limit allows; quantity is the smallest, and limited_by names it.
    limits: dict[Literal["risk", "cash", "position", "concentration", "liquidity"], int] = {}
    limited_by: Literal["risk", "cash", "position", "concentration", "liquidity"] | None = None
    portfolio_share: float | None = None  # the buy as a share of the portfolio


class BuyRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=12)
    quantity: int = Field(gt=0)
    stop_loss: float = Field(gt=0)
    take_profit: float = Field(gt=0)
    recommendation_id: str | None = None


class HoldingOut(BaseModel):
    ticker: str
    description: str
    type: str
    currency: Literal["ARS", "USD"]
    quantity: float
    last_price: float
    avg_price: float
    value: float
    gain_pct: float
    gain_amount: float
    day_change_pct: float


class PortfolioOut(BaseModel):
    captured_at: datetime  # when these prices were read from IOL
    holdings: list[HoldingOut]


class HitStats(BaseModel):
    n: int
    hits: int
    hit_rate: float | None
    avg_return: float | None


class SignalStats(BaseModel):
    signal: Literal["news", "markets", "trend", "context", "gap", "macro"]
    n: int  # graded recommendations where this signal pointed somewhere
    hits: int  # ... and the price moved that way (open -> close)
    hit_rate: float | None
    avg_when_up: float | None  # average move when the signal said up
    avg_when_down: float | None  # average move when it said down


class TrackRecordSummary(BaseModel):
    overall: HitStats
    action: dict[Action, HitStats]
    driver: dict[str, HitStats]
    confidence: dict[str, HitStats]
    held: dict[str, HitStats]


class CalibrationBucket(BaseModel):
    action: Action
    held: bool
    score_min: float  # |score| range, inclusive
    score_max: float  # exclusive
    n: int
    hits: int
    hit_rate: float


class ModelInfo(BaseModel):
    """The scoring model's constants, so the "Cómo decide" page always matches the code."""

    weights: dict[str, float]
    buy_threshold: float
    sell_threshold_held: float
    broad_weight: float
    sector_weight: float
    sectors: dict[str, list[str]]
    news_half_life_hours: float
    news_max_age_hours: float
    priced_in_full: float
    concentration_limit: float
    concentration_penalty: float
    concentration_max: float
    risk_per_trade: float
    max_position: float
    max_volume_share: float
    calibration_min_cases: int
