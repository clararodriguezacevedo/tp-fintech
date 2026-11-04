"""Rows of our Supabase tables (see supabase/migrations). Also used as API response models."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

Action = Literal["buy", "sell", "keep"]
Direction = Literal["up", "down", "unknown"]
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
    strength: Strength | None = None  # only in the first model's tags
    mention: str | None = None  # the words of the text that name the asset
    tag_version: int = 1
    reason: str | None = None
    created_at: datetime


class Evidence(BaseModel):
    """One news item or market behind a recommendation."""

    kind: Literal["news", "market"]
    item_id: str
    title: str
    url: str | None = None
    direction: Direction
    reason: str
    value: float = 0.0  # -1 to +1: what it says
    weight: float = 1.0  # how much it counts
    contribution: float  # value * weight
    detail: str = ""
    since: datetime | None = None  # news: published; market: start of its 24h move
    sources: int = 1  # how many outlets ran the same story
    via: str | None = None  # the factor a market reaches the ticker through


class SignalBreakdown(BaseModel):
    news: float
    markets: float
    asset_class: Literal["stocks", "bonds", "us"] | None = None  # what it's ranked against
    rank: int | None = None  # place within its class, among those with evidence
    rank_of: int | None = None
    top_rank: bool = False  # in the top share of its class
    concentration: float = 0.0  # first model only: penalty in the score
    change_3m: float | None = None  # price change over the last 3 months (shown, not scored)
    from_high: float | None = None  # distance from the 3-month high, <= 0 (shown, not scored)
    macro: float = 0.0  # riesgo país or CCL dollar moving its way: measured, not in the score
    macro_source: Literal["riesgo_pais", "ccl"] | None = None
    macro_level: float | None = None  # riesgo país points or CCL pesos
    macro_change: float | None = None  # its change over 5 trading days
    event_kind: Literal["dividend", "coupon"] | None = None  # next payment detaching soon
    event_date: date | None = None
    event_yield: float | None = None
    risk_level: int | None = None  # 1 bajo, 2 medio, 3 alto (app.analysis.suitability)
    volatility: float | None = None  # annualized, the basis of risk_level
    profile: Literal["conservador", "moderado", "arriesgado"] | None = None  # the user's, when scored
    out_of_profile: bool = False  # above the profile: never recommended to buy


class RecommendationRow(Row):
    id: str
    ticker: str
    action: Action
    kind: Literal["live", "daily"]
    score: float
    model_version: int = 1
    held: bool
    signal_breakdown: SignalBreakdown
    evidence: list[Evidence]
    price_at_rec: float | None = None
    target_date: date
    open_on_target: float | None = None
    close_on_target: float | None = None
    realized_return: float | None = None  # open -> close of the target day
    close_return: float | None = None  # previous close -> close, plus any dividend detached
    excess_return: float | None = None  # realized_return minus the day's median of its class
    event_yield: float | None = None  # dividend added back on an ex-date
    hit: bool | None = None
    evaluated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class TradeRow(Row):
    id: str
    ticker: str
    market: str
    quantity: int
    side: Literal["buy", "sell"] = "buy"
    entry_price: float
    stop_loss: float | None = None  # buys only
    take_profit: float | None = None  # buys only
    status: TradeStatus
    live: bool
    cost_basis: float | None = None  # sells: what the units sold had cost
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
