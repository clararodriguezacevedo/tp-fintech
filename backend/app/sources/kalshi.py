"""Kalshi public market data. REST reads need no API key (the WebSocket does)."""

import httpx

from app.models.domain import MarketRecord
from app.models.kalshi import EventsPage

BASE = "https://api.elections.kalshi.com/trade-api/v2"

# Sports, weather and entertainment don't move Argentine tickers.
RELEVANT_CATEGORIES = {"Economics", "Financials", "Politics", "Elections", "Companies"}


def fetch_markets(
    client: httpx.Client, max_pages: int = 5, min_volume_24h: float = 1
) -> list[MarketRecord]:
    """Open markets in relevant categories that traded in the last 24h, normalized.

    Most open Kalshi markets (around 90%) have no trades on a given day; skipping them keeps
    tagging and storage manageable.
    """
    out: list[MarketRecord] = []
    cursor = ""
    for _ in range(max_pages):
        params: dict[str, str | int] = {"status": "open", "with_nested_markets": "true", "limit": 200}
        if cursor:
            params["cursor"] = cursor
        r = client.get(f"{BASE}/events", params=params)
        r.raise_for_status()
        page = EventsPage.model_validate(r.json())
        for e in page.events:
            if e.category not in RELEVANT_CATEGORIES:
                continue
            for m in e.markets:
                if m.volume_24h_fp < min_volume_24h:
                    continue
                title = e.title
                if m.yes_sub_title and len(e.markets) > 1:
                    title = f"{title}: {m.yes_sub_title}"
                out.append(MarketRecord(
                    source="kalshi",
                    external_id=m.ticker,
                    event_key=f"k:{e.event_ticker}",
                    title=title,
                    url=f"https://kalshi.com/markets/{e.series_ticker.lower()}",
                    category=e.category,
                    probability=m.probability,
                    change_24h=m.change_24h,
                    volume_24h=m.volume_24h_fp,
                    end_date=m.close_time,
                ))
        cursor = page.cursor
        if not cursor:
            break
    return out
