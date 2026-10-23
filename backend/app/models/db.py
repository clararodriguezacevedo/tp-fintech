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
    contribution: float  # after discounting what the price already did
    detail: str = ""
    broad: bool = False  # came from a MERVAL / BONOS tag, applied at half weight
    since: datetime | None = None  # news: published; market: start of its 24h move
    move_since: float | None = None  # price move of the ticker since `since`
    priced_in: float = 0.0  # 0..1, share of the signal the price already reflected
    sources: int = 1  # how many outlets ran the same story


class SignalBreakdown(BaseModel):
    news: float
    markets: float
    trend: float
    context: float = 0.0  # whole market's trend (Merval leaders, bonds or S&P 500)
    gap: float = 0.0  # CEDEAR cheap (+) or expensive (-) versus its US share and the dollar


class RecommendationRow(Row):
    id: str
    ticker: str
    action: Action
    kind: Literal["live", "daily"]
    score: float
    confidence: float
    driver: Literal["news", "markets", "trend", "context", "gap"] | None = None
    held: bool
    signal_breakdown: SignalBreakdown
    evidence: list[Evidence]
    price_at_rec: float | None = None
    target_date: date
    open_on_target: float | None = None
    close_on_target: float | None = None
    realized_return: float | None = None  # open -> close of the target day
    close_return: float | None = None  # previous close -> close
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
