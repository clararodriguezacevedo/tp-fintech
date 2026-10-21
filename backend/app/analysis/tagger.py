"""Links news and prediction markets to tickers with Gemini (free tier)."""

import logging
from typing import Literal

from google import genai
from google.genai import errors, types
from pydantic import BaseModel

from app.config import get_settings

# Tickers we can actually trade on IOL. ADRs map to their local BYMA ticker.
UNIVERSE = {
    "acciones": ["GGAL", "YPFD", "PAMP", "BMA", "TXAR", "ALUA", "CEPU", "TGSU2", "LOMA", "SUPV",
                 "BBAR", "CRES", "EDN", "TECO2", "VALO", "COME", "BYMA", "METR", "TGNO4", "TRAN"],
    "cedears": ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "MELI", "KO", "XOM",
                "JPM", "VIST", "SPY", "QQQ", "GLD", "BRKB", "WMT", "DIS", "BABA", "PBR"],
    "bonos": ["AL30", "GD30", "AL35", "GD35", "GD41", "AE38"],
}
ALL_TICKERS = sorted({t for group in UNIVERSE.values() for t in group})

log = logging.getLogger(__name__)

SYSTEM = f"""You tag financial news and prediction markets for an Argentine retail investor.

For each item, list the tickers it could move on the next trading day, with direction and
strength. Only use tickers from this list: {", ".join(ALL_TICKERS)}.
Use "MERVAL" for broad Argentine equity impact and "BONOS" for broad sovereign bond impact.

For a prediction market, the direction refers to the YES outcome becoming more likely.
Return an empty ticker list when nothing on the list is plausibly affected; most sports,
celebrity and weather items fall here.

Write the summary in Spanish, one or two plain sentences an average investor understands."""


class TickerImpact(BaseModel):
    ticker: str
    direction: Literal["up", "down"]
    strength: Literal["low", "medium", "high"]
    reason: str


class TaggedItem(BaseModel):
    id: str
    summary: str
    impacts: list[TickerImpact]


class TagBatch(BaseModel):
    items: list[TaggedItem]


_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=get_settings().gemini_api_key)
    return _client


def tag_items(items: list[dict]) -> list[TaggedItem]:
    """items: dicts with id, kind ("news" | "market"), title, text. Send ~20 per call."""
    if not items:
        return []
    lines = [
        f"[{it['id']}] ({it['kind']}) {it['title']}\n{it.get('text', '')[:600]}" for it in items
    ]
    try:
        response = _get_client().models.generate_content(
            model=get_settings().tagger_model,
            contents="\n\n".join(lines),
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM,
                response_mime_type="application/json",
                response_schema=TagBatch,
            ),
        )
    except errors.APIError as e:
        # Free tier quota errors (429) land here; the items stay untagged for the next cycle.
        log.warning("tagging failed: %s", e)
        return []
    batch = response.parsed
    if not isinstance(batch, TagBatch):
        return []
    allowed = set(ALL_TICKERS) | {"MERVAL", "BONOS"}
    for item in batch.items:
        item.impacts = [i for i in item.impacts if i.ticker in allowed]
    return batch.items
