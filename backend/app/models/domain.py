"""Our own normalized records, as written to Supabase by the collectors."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class MarketRecord(BaseModel):
    """A prediction market from either exchange, normalized. Row of prediction_markets."""

    source: Literal["polymarket", "kalshi"]
    external_id: str
    event_key: str  # markets of the same real-world event share it
    title: str
    url: str
    category: str | None = None
    probability: float | None = None
    change_1h: float | None = None
    change_24h: float | None = None
    volume_24h: float | None = None
    end_date: datetime | None = None
    clob_token_ids: list[str] | None = None


class NewsRecord(BaseModel):
    """A news article from RSS or GDELT. Row of news_items."""

    external_id: str
    source: str
    title: str
    summary: str = ""
    url: str
    published_at: datetime | None = None
