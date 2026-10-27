"""Polymarket public market data. No credentials needed for any of these reads."""

import logging

import httpx
from pydantic import TypeAdapter, ValidationError

from app.models.domain import MarketRecord
from app.models.polymarket import GammaMarket, PriceHistory, PricePoint, Trade

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
DATA = "https://data-api.polymarket.com"

log = logging.getLogger(__name__)


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


# The most traded markets overall are mostly sports and US races, which move no Argentine
# ticker. These topics are fetched on top of them. An unknown slug just returns nothing.
TOPICS = ("economy", "finance", "business", "fed-rates", "tech", "crypto", "geopolitics", "argentina")
PER_TOPIC = 20


def fetch_topic_markets(client: httpx.Client, topic: str, limit: int = PER_TOPIC) -> list[GammaMarket]:
    """Open markets of the most traded events tagged `topic`."""
    r = client.get(
        f"{GAMMA}/events",
        params={"active": "true", "closed": "false", "tag_slug": topic, "order": "volume24hr",
                "ascending": "false", "limit": limit},
    )
    r.raise_for_status()
    out = []
    for event in r.json():
        ref = {"id": str(event.get("id")), "slug": event.get("slug", ""), "title": event.get("title", "")}
        for m in event.get("markets") or []:
            try:
                market = GammaMarket.model_validate(m | {"events": [ref]})
            except ValidationError:
                continue
            if market.active and not market.closed:
                out.append(market)
    return out


def fetch_markets(client: httpx.Client, limit: int = 100) -> list[MarketRecord]:
    raw = {m.condition_id: m for m in fetch_raw_markets(client, limit)}
    for topic in TOPICS:
        try:
            for m in fetch_topic_markets(client, topic):
                raw.setdefault(m.condition_id, m)
        except (httpx.HTTPError, ValueError):
            log.warning("no Polymarket markets for topic %s", topic)
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
        for m in raw.values()
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
