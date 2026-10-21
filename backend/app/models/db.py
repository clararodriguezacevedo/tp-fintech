"""Rows of our Supabase tables (see supabase/migrations). Also used as API response models."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

Action = Literal["buy", "sell", "keep"]
Direction = Literal["up", "down"]
Strength = Literal["low", "medium", "high"]
TradeStatus = Literal[
    "queued", "sent", "filled", "stopped_out", "took_profit", "closed", "cancelled", "failed"
]


class Row(BaseModel):
    model_config = ConfigDict(extra="ignore")


class NewsRow(Row):
    id: str
    external_id: str
    source: str
    title: str
    summary: str | None = None
    url: str
    published_at: datetime | None = None
    ai_summary: str | None = None
    tagged_at: datetime | None = None
    created_at: datetime


class MarketRow(Row):
    id: str
    source: Literal["polymarket", "kalshi"]
    external_id: str
    event_key: str | None = None
    title: str
    url: str | None = None
    category: str | None = None
    end_date: datetime | None = None
    clob_token_ids: list[str] | None = None
    probability: float | None = None
    change_1h: float | None = None
    change_24h: float | None = None
    volume_24h: float | None = None
    ai_summary: str | None = None
    tagged_at: datetime | None = None
    updated_at: datetime


class SnapshotRow(Row):
    market_id: str
    probability: float | None = None
    volume_24h: float | None = None
    captured_at: datetime


class TickerImpactRow(Row):
    id: str
    item_kind: Literal["news", "market"]
    item_id: str
    ticker: str
    direction: Direction
    strength: Strength
    reason: str | None = None
    created_at: datetime


class Evidence(BaseModel):
    """One news item or market behind a recommendation."""

    kind: Literal["news", "market"]
    item_id: str
    title: str
    url: str | None = None
    direction: Direction
    strength: Strength
    reason: str
    contribution: float
    detail: str = ""
    broad: bool = False  # came from a MERVAL / BONOS tag, applied at half weight


class SignalBreakdown(BaseModel):
    news: float
    markets: float
    trend: float


class RecommendationRow(Row):
    id: str
    ticker: str
    action: Action
    kind: Literal["live", "daily"]
    score: float
    confidence: float
    driver: Literal["news", "markets", "trend"] | None = None
    held: bool
    signal_breakdown: SignalBreakdown
    evidence: list[Evidence]
    price_at_rec: float | None = None
    target_date: date
    close_on_target: float | None = None
    realized_return: float | None = None
    hit: bool | None = None
    evaluated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class TradeRow(Row):
    id: str
    ticker: str
    market: str
    quantity: int
    entry_price: float
    stop_loss: float
    take_profit: float
    status: TradeStatus
    live: bool
    fill_price: float | None = None
    filled_at: datetime | None = None
    exit_price: float | None = None
    closed_at: datetime | None = None
    realized_pnl: float | None = None
    iol_order_number: int | None = None
    exit_order_number: int | None = None
    error: str | None = None
    recommendation_id: str | None = None
    created_at: datetime
    updated_at: datetime
