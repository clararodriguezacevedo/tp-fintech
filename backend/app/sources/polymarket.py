"""Polymarket public market data. No credentials needed for any of these reads."""

import json

import httpx

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
DATA = "https://data-api.polymarket.com"


def _yes_price(market: dict) -> float | None:
    # Gamma returns outcomePrices as a JSON-encoded string, e.g. '["0.62", "0.38"]'.
    try:
        return float(json.loads(market["outcomePrices"])[0])
    except (KeyError, IndexError, ValueError, TypeError):
        return None


def fetch_markets(client: httpx.Client, limit: int = 100) -> list[dict]:
    """Most traded open markets in the last 24h, normalized to our schema."""
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
    out = []
    for m in r.json():
        out.append(
            {
                "source": "polymarket",
                "external_id": m["conditionId"],
                "title": m["question"],
                "url": f"https://polymarket.com/event/{m.get('slug', '')}",
                "probability": _yes_price(m),
                "change_1h": m.get("oneHourPriceChange"),
                "change_24h": m.get("oneDayPriceChange"),
                "volume_24h": m.get("volume24hr"),
                "end_date": m.get("endDate"),
                "clob_token_ids": json.loads(m.get("clobTokenIds") or "[]"),
            }
        )
    return out


def fetch_price_history(client: httpx.Client, token_id: str, interval: str = "1w") -> list[dict]:
    """Probability over time for one outcome token, for the evolution chart."""
    r = client.get(
        f"{CLOB}/prices-history",
        params={"market": token_id, "interval": interval, "fidelity": 60},
    )
    r.raise_for_status()
    return [{"t": p["t"], "p": p["p"]} for p in r.json().get("history", [])]


def fetch_large_trades(client: httpx.Client, condition_id: str, min_usd: float = 10_000) -> list[dict]:
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
    return [
        {
            "side": t.get("side"),
            "outcome": t.get("outcome"),
            "size": t.get("size"),
            "price": t.get("price"),
            "usd": float(t.get("size", 0)) * float(t.get("price", 0)),
            "timestamp": t.get("timestamp"),
        }
        for t in r.json()
    ]
