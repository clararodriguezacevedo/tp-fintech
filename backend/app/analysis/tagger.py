"""Links news and prediction markets to tickers with Gemini (free tier)."""

import logging
import re
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

SYSTEM = """You tag financial news and prediction markets for an Argentine retail investor.

For each item, list the tickers it could move on the next trading day, with direction and
strength. Only use tickers from this list: {tickers}.
Use "MERVAL" for broad Argentine equity impact and "BONOS" for broad sovereign bond impact.
{holdings}
For a prediction market, the direction refers to the YES outcome becoming more likely.
Return an empty ticker list when nothing on the list is plausibly affected; most sports,
celebrity and weather items fall here.
Also return an empty ticker list for market wrap-ups that only report how prices already moved
("así cerró el mercado", "las acciones subieron hasta 6%", "stocks fell on Friday"): they carry
no new information, the move is already in the price.
The same for previews of an event whose outcome is unknown ("Big Tech's earnings are on deck",
"what to watch this week", "se esperan los balances"): an upcoming report is not good or bad
news until its numbers are out. Tag the result once it is reported, not the wait for it.

Write the summary in Spanish, one or two plain sentences an average investor understands."""


def _system(holdings: dict[str, str]) -> str:
    """holdings: ticker -> description, for positions outside the base universe."""
    extra = ""
    if holdings:
        lines = "\n".join(f"- {t}: {d}" for t, d in sorted(holdings.items()))
        extra = f"\nThe investor also holds these, which are on the list too:\n{lines}\n"
    return SYSTEM.format(tickers=", ".join(sorted(set(ALL_TICKERS) | set(holdings))), holdings=extra)


class TagInput(BaseModel):
    id: str
    kind: Literal["news", "market"]
    title: str
    text: str = ""


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


def tag_items(items: list[TagInput], holdings: dict[str, str] | None = None) -> list[TaggedItem]:
    """Tag a batch of news and markets. Send ~20 per call.

    holdings: ticker -> description of the user's positions, so they can be tagged too.
    """
    holdings = holdings or {}
    if not items:
        return []
    lines = [f"[{it.id}] ({it.kind}) {it.title}\n{it.text[:600]}" for it in items]
    try:
        response = _get_client().models.generate_content(
            model=get_settings().tagger_model,
            contents="\n\n".join(lines),
            config=types.GenerateContentConfig(
                system_instruction=_system(holdings),
                response_mime_type="application/json",
                response_schema=TagBatch,
            ),
        )
    except errors.APIError as e:
        # Free tier quota errors (429) land here; the items stay untagged for the next cycle.
        log.warning("tagging failed: %s", e)
        if e.code == 429:
            from app import alerts  # avoid an import cycle

            alerts.gemini_quota()
        return []
    batch = response.parsed
    if not isinstance(batch, TagBatch):
        return []
    allowed = set(ALL_TICKERS) | set(holdings) | {"MERVAL", "BONOS"}
    for item in batch.items:
        item.impacts = [i for i in item.impacts if i.ticker in allowed]
    # Gemini sometimes writes "3" for an accented letter ("posici3n", "petr3leo"). Those items
    # are left out, so they stay untagged and are tagged again on the next cycle.
    clean = [it for it in batch.items if not has_broken_accents(it)]
    if len(clean) < len(batch.items):
        log.warning("dropped %d tagged items with broken accents", len(batch.items) - len(clean))
    return clean


_BROKEN = re.compile(r"[A-Za-záéíóúñÁÉÍÓÚÑ]3[a-záéíóúñ]")


def has_broken_accents(item: TaggedItem) -> bool:
    return any(_BROKEN.search(text) for text in [item.summary, *(i.reason for i in item.impacts)])
