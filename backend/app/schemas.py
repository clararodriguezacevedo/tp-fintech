"""Request and response models of our own API that aren't table rows (those are in
app.models.db). FastAPI publishes all of them in /openapi.json, which the frontend uses to
generate its zod schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.db import Action


class Health(BaseModel):
    ok: bool
    market_open: bool
    next_open: datetime
    live_trading: bool
    mode: Literal["paper", "live"]


class ProbabilityPoint(BaseModel):
    t: datetime
    p: float = Field(ge=0, le=1)


class PortfolioValuePoint(BaseModel):
    t: datetime
    value: float


class TradePlan(BaseModel):
    entry: float
    stop_loss: float
    take_profit: float
    quantity: int
    max_loss: float
    market_open: bool


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
    quantity: float
    last_price: float
    avg_price: float
    value: float
    gain_pct: float


class HitStats(BaseModel):
    n: int
    hits: int
    hit_rate: float | None
    avg_return: float | None


class TrackRecordSummary(BaseModel):
    overall: HitStats
    action: dict[Action, HitStats]
    driver: dict[str, HitStats]
    confidence: dict[str, HitStats]
    held: dict[str, HitStats]
