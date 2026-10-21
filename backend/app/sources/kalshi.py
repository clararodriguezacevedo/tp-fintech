"""Kalshi public market data. REST reads need no API key (the WebSocket does)."""

import httpx

BASE = "https://api.elections.kalshi.com/trade-api/v2"

# Sports, weather and entertainment don't move Argentine tickers.
RELEVANT_CATEGORIES = {"Economics", "Financials", "Politics", "Elections", "Companies"}


def _f(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _probability(m: dict) -> float | None:
    bid, ask = _f(m.get("yes_bid_dollars")), _f(m.get("yes_ask_dollars"))
    if bid and ask:
        return (bid + ask) / 2
    return _f(m.get("last_price_dollars"))


def fetch_markets(client: httpx.Client, max_pages: int = 5, min_volume_24h: float = 1) -> list[dict]:
    """Open markets in relevant categories that traded in the last 24h, normalized to our schema.

    Most open Kalshi markets (around 90%) have no trades on a given day; skipping them keeps
    tagging and storage manageable.
    """
    out, cursor = [], None
    for _ in range(max_pages):
        params = {"status": "open", "with_nested_markets": "true", "limit": 200}
        if cursor:
            params["cursor"] = cursor
        r = client.get(f"{BASE}/events", params=params)
        r.raise_for_status()
        data = r.json()
        for e in data["events"]:
            if e.get("category") not in RELEVANT_CATEGORIES:
                continue
            for m in e.get("markets", []):
                if (_f(m.get("volume_24h_fp")) or 0) < min_volume_24h:
                    continue
                last, prev = _f(m.get("last_price_dollars")), _f(m.get("previous_price_dollars"))
                title = e["title"]
                if m.get("yes_sub_title") and len(e["markets"]) > 1:
                    title = f"{title}: {m['yes_sub_title']}"
                out.append(
                    {
                        "source": "kalshi",
                        "external_id": m["ticker"],
                        "title": title,
                        "url": f"https://kalshi.com/markets/{e['series_ticker'].lower()}",
                        "probability": _probability(m),
                        "change_1h": None,
                        "change_24h": (last - prev) if last is not None and prev is not None else None,
                        "volume_24h": _f(m.get("volume_24h_fp")),
                        "end_date": m.get("close_time"),
                        "category": e.get("category"),
                    }
                )
        cursor = data.get("cursor")
        if not cursor:
            break
    return out
