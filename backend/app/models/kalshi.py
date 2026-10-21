"""Kalshi trade-api v2 responses, typed from real responses.

Kalshi sends prices and volumes as decimal strings ("0.8900"); pydantic converts them.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class KalshiModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class KalshiMarket(KalshiModel):
    ticker: str
    event_ticker: str
    title: str
    yes_sub_title: str = ""
    status: str
    close_time: datetime
    last_price_dollars: float | None = None
    previous_price_dollars: float | None = None
    yes_bid_dollars: float | None = None
    yes_ask_dollars: float | None = None
    volume_24h_fp: float = 0
    volume_fp: float = 0
    open_interest_fp: float = 0

    @property
    def probability(self) -> float | None:
        if self.yes_bid_dollars and self.yes_ask_dollars:
            return (self.yes_bid_dollars + self.yes_ask_dollars) / 2
        return self.last_price_dollars

    @property
    def change_24h(self) -> float | None:
        if self.last_price_dollars is None or self.previous_price_dollars is None:
            return None
        return self.last_price_dollars - self.previous_price_dollars


class KalshiEvent(KalshiModel):
    event_ticker: str
    series_ticker: str
    category: str
    title: str
    sub_title: str = ""
    mutually_exclusive: bool
    markets: list[KalshiMarket] = []


class EventsPage(KalshiModel):
    """GET /trade-api/v2/events?with_nested_markets=true"""

    events: list[KalshiEvent]
    cursor: str = ""
