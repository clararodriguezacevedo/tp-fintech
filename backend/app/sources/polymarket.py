"""Polymarket public market data. No credentials needed for any of these reads."""

import httpx
from pydantic import TypeAdapter

from app.models.domain import MarketRecord
from app.models.polymarket import GammaMarket, PriceHistory, PricePoint, Trade

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
DATA = "https://data-api.polymarket.com"


def fetch_raw_markets(client: httpx.Client, limit: int = 100) -> list[GammaMarket]:
    """Most traded open markets in the last 24h."""
    r = client.get(
        f"{GAMMA}/markets",
        params={
            "active": "true",
            "closed": "false",
            "order": "volume24hr",
            "ascending": "false",
            "limit": limit,
        },
    )
    r.raise_for_status()
    return TypeAdapter(list[GammaMarket]).validate_python(r.json())


def fetch_markets(client: httpx.Client, limit: int = 100) -> list[MarketRecord]:
    return [
        MarketRecord(
            source="polymarket",
            external_id=m.condition_id,
            event_key=m.event_key,
            title=m.question,
            url=f"https://polymarket.com/event/{m.events[0].slug if m.events else m.slug}",
            probability=m.yes_price,
            change_1h=m.one_hour_price_change,
            change_24h=m.one_day_price_change,
            volume_24h=m.volume_24hr,
            end_date=m.end_date,
            clob_token_ids=m.clob_token_ids,
        )
        for m in fetch_raw_markets(client, limit)
    ]


def fetch_price_history(client: httpx.Client, token_id: str, interval: str = "1w") -> list[PricePoint]:
    """Probability over time for one outcome token, for the evolution chart."""
    r = client.get(
        f"{CLOB}/prices-history",
        params={"market": token_id, "interval": interval, "fidelity": 60},
    )
    r.raise_for_status()
    return PriceHistory.model_validate(r.json()).history


def fetch_large_trades(client: httpx.Client, condition_id: str, min_usd: float = 10_000) -> list[Trade]:
    """Recent trades above min_usd on one market (large-bet alerts)."""
    r = client.get(
        f"{DATA}/trades",
        params={
            "market": condition_id,
            "filterType": "CASH",
            "filterAmount": min_usd,
            "limit": 50,
        },
    )
    r.raise_for_status()
    return TypeAdapter(list[Trade]).validate_python(r.json())
