"""Polymarket public API responses (Gamma, CLOB, Data), typed from real responses."""

import json
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator
from pydantic.alias_generators import to_camel


class PMModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")


class GammaEvent(PMModel):
    id: str
    slug: str
    title: str


class GammaMarket(PMModel):
    """GET gamma-api.polymarket.com/markets"""

    id: str
    question: str
    condition_id: str
    slug: str
    end_date: datetime | None = None
    outcomes: list[str]
    outcome_prices: list[float]
    clob_token_ids: list[str]
    volume_24hr: float = 0
    one_hour_price_change: float | None = None
    one_day_price_change: float | None = None
    one_week_price_change: float | None = None
    last_trade_price: float | None = None
    best_bid: float | None = None
    best_ask: float | None = None
    active: bool
    closed: bool
    events: list[GammaEvent] = []

    # Gamma sends these three as JSON-encoded strings, e.g. '["0.62", "0.38"]'.
    @field_validator("outcomes", "outcome_prices", "clob_token_ids", mode="before")
    @classmethod
    def _decode_json_list(cls, v):
        return json.loads(v) if isinstance(v, str) else v

    @property
    def yes_price(self) -> float | None:
        return self.outcome_prices[0] if self.outcome_prices else None

    @property
    def event_key(self) -> str:
        """Markets of the same event (e.g. "ceasefire through Oct 22 / 24 / 31") share this."""
        return f"pm:{self.events[0].id}" if self.events else f"pm:{self.condition_id}"


class PricePoint(BaseModel):
    t: int  # unix seconds
    p: float  # probability 0..1


class PriceHistory(BaseModel):
    """GET clob.polymarket.com/prices-history"""

    history: list[PricePoint]


class Trade(PMModel):
    """GET data-api.polymarket.com/trades"""

    side: str  # "BUY" | "SELL"
    asset: str
    condition_id: str
    size: float
    price: float
    timestamp: int
    title: str
    slug: str
    event_slug: str
    outcome: str
    outcome_index: int
    transaction_hash: str

    @property
    def usd(self) -> float:
        return self.size * self.price
