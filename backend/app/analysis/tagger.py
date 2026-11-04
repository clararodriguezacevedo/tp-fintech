"""What Gemini does: one narrow question per item. It reads, it doesn't recommend.

  news     which listed assets the text is explicitly about, and whether it's good, bad or unclear
           for each one's price over the next 1 to 3 days
  markets  what YES means, and which asset or factor (app.analysis.factors) it pushes up or down

Its answer goes through checks that don't depend on it: an asset tagged has to be named in the text
in words that belong to that asset, and a bet on an asset's own price is discarded.
"""

import html
import logging
import re
import unicodedata
from typing import Literal

from google import genai
from google.genai import errors, types
from pydantic import BaseModel

from app.analysis import factors
from app.config import get_settings

# The short list used until IOL's full universe is loaded (app.universe).
# ADRs map to their local BYMA ticker.
UNIVERSE = {
    "acciones": ["GGAL", "YPFD", "PAMP", "BMA", "TXAR", "ALUA", "CEPU", "TGSU2", "LOMA", "SUPV",
                 "BBAR", "CRES", "EDN", "TECO2", "VALO", "COME", "BYMA", "METR", "TGNO4", "TRAN"],
    "cedears": ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "MELI", "KO", "XOM",
                "JPM", "VIST", "SPY", "QQQ", "GLD", "BRKB", "WMT", "DIS", "BABA", "PBR"],
    "bonos": ["AL30", "GD30", "AL35", "GD35", "GD41", "AE38"],
}
ALL_TICKERS = sorted({t for group in UNIVERSE.values() for t in group})

log = logging.getLogger(__name__)

NAME_CHARS = 28  # of each asset's name in the prompt, to keep it small

NEWS_SYSTEM = """You read financial news for an Argentine retail investor.

For each item, list ONLY the assets the text is explicitly about: it names the company, its
products or its executives, or the fund or bond itself. Assets: {tickers}.
{holdings}
Do not infer. News about oil is not about Exxon unless it names Exxon. News about the market, the
economy, a sector or a competitor is about no asset: return an empty list.

For each asset:
- direction: is this good ("up"), bad ("down") or unclear ("unknown") for that asset's price over
  the next 1 to 3 days? Use "unknown" whenever you are not sure.
- mention: the exact words of the text that name it, copied literally.
- reason: one short sentence in Spanish.

Return an empty list for market wrap-ups that only report how prices already moved ("así cerró el
mercado", "las acciones subieron hasta 6%", "stocks fell on Friday"): the move is already in the
price. A preview of an upcoming event counts only if it leans one way (results expected to beat or
miss); if it only announces the event, return an empty list.

Answer for every item, with its id, even when its list is empty.
Write the summary in Spanish, one or two plain sentences an average investor understands."""

MARKET_SYSTEM = """You read prediction markets for an Argentine retail investor. Each one is a
yes/no question. Work out what its YES coming true would mean, and say what it pushes.

Targets, use only these:
- a factor, for a question about the world:
{factors}
- an asset, only if the question names that company for something other than its share price.
  Assets: {tickers}.
{holdings}
For each target:
- direction: does YES push it up ("up") or down ("down")? For a factor, up means the factor rises:
  a Fed cut pushes F:US_RATES down, oil hitting a low pushes F:OIL down, a default or a crisis in
  Argentina pushes F:AR_RISK up. For an asset, up means good for its price.
- "unknown" for a range ("between 400 and 425"), a ranking among peers or anything without a clear
  direction.
- mention: for an asset, the exact words of the question that name it. Empty for a factor.
- reason: in Spanish, what YES means, as a fact that may happen ("Que el petróleo supere USD 115
  antes del 30/11"). No opinions.

Return an empty list when:
- it bets on where a company's share price or a stock index lands ("Apple closes above $200", "S&P
  500 up or down", "Palantir hits $162"): it only repeats the price, which already moved;
- it's about sports, celebrities, weather, a contest with no effect on earnings ("best AI model on
  a leaderboard") or when a product or an AI model comes out.

Answer for every item, with its id, even when its list is empty.
Write the summary in Spanish: what the market asks, in one plain sentence."""


def _factor_list() -> str:
    return "\n".join(f"  {k}: {f.label}" for k, f in factors.FACTORS.items())


def _system(kind: str, holdings: dict[str, str], universe: dict[str, str] | None = None) -> str:
    """holdings: ticker -> description, for positions outside the base universe.
    universe: ticker -> name of everything IOL offers; the base list if empty."""
    extra = ""
    if holdings:
        lines = "\n".join(f"- {t}: {d}" for t, d in sorted(holdings.items()))
        extra = f"\nThe investor also holds these, which are on the list too:\n{lines}\n"
    if universe:
        # With names: nobody knows a local ticker or a small CEDEAR by its symbol alone.
        listed = "; ".join(f"{t} ({n[:NAME_CHARS]})" for t, n in sorted(universe.items()))
    else:
        listed = ", ".join(sorted(set(ALL_TICKERS) | set(holdings)))
    if kind == "market":
        return MARKET_SYSTEM.format(factors=_factor_list(), tickers=listed, holdings=extra)
    return NEWS_SYSTEM.format(tickers=listed, holdings=extra)


def prompts_for_display() -> dict[str, str]:
    """The instructions Gemini gets, to show them on the site as they are."""
    assets = "[the assets IOL offers, each with its name]"
    return {
        "news": NEWS_SYSTEM.format(tickers=assets, holdings=""),
        "market": MARKET_SYSTEM.format(factors=_factor_list(), tickers=assets, holdings=""),
    }


class TagInput(BaseModel):
    id: str
    kind: Literal["news", "market"]
    title: str
    text: str = ""


class TickerImpact(BaseModel):
    ticker: str  # an asset, or a factor for markets
    direction: Literal["up", "down", "unknown"]
    mention: str = ""
    reason: str


class TaggedItem(BaseModel):
    id: str
    summary: str
    impacts: list[TickerImpact]


class TagBatch(BaseModel):
    items: list[TaggedItem]


# Checks that don't depend on Gemini


def plain(text: str) -> str:
    return unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()


# How the press calls an asset, when its name in IOL doesn't help ("Bbva", "Vista Oil & Gas Sab De").
ALIASES = {
    "QQQ": ["nasdaq"], "SPY": ["s&p", "sp500", "sp 500"], "DIA": ["dow jones"], "YPFD": ["ypf"],
    "VIST": ["vista"], "GGAL": ["galicia"], "BBAR": ["bbva", "frances"], "BMA": ["macro"], "SUPV": ["supervielle"],
    "PAMP": ["pampa"], "TECO2": ["telecom"], "TXAR": ["ternium"], "ALUA": ["aluar"], "EDN": ["edenor"],
    "CEPU": ["central puerto"], "TGSU2": ["tgs", "gas del sur"], "TGNO4": ["tgn", "gas del norte"],
    "COME": ["comercial del plata"], "LOMA": ["loma negra"], "METR": ["metrogas"], "CRES": ["cresud"],
    "VALO": ["grupo valores"], "ECOG": ["ecogas"], "TRAN": ["transener"], "MELI": ["mercado libre", "mercadolibre", "meli"],
    "META": ["meta", "facebook", "instagram", "whatsapp"], "GOOGL": ["google", "alphabet", "youtube"],
    "MSFT": ["microsoft", "azure"], "AAPL": ["apple", "iphone"], "AMZN": ["amazon", "aws"], "TSLA": ["tesla"],
    "NVDA": ["nvidia"], "TSM": ["tsmc", "taiwan semiconductor"], "NU": ["nubank", "nu holdings"], "XOM": ["exxon"],
    "BRKB": ["berkshire"], "JPM": ["jpmorgan", "jp morgan"], "GLD": ["oro", "gold"], "AL30": ["bonar 2030", "bonares"],
    "AL35": ["bonar 2035", "bonares"], "GD30": ["global 2030", "globales"], "GD35": ["global 2035", "globales"],
    "XLE": ["energy select"], "XLK": ["technology select"], "XLP": ["consumer staples select"],
}
# Words of IOL's names that say nothing about which asset it is.
GENERIC = set(
    "banco bono bonos tesoro nacional grupo financiero holding holdings corp corporation company inc ltd "
    "trust etf fund fondo select sector state street group sab gas oil energy energia rep argentina usd step "
    "tasa dual global class technology consumer staples the del las los and ishares spdr invesco".split()
)


def names_for(ticker: str, name: str = "") -> set[str]:
    """Words that identify an asset: its ticker, its aliases and what's particular in its name."""
    words = {w for w in re.findall(r"[a-z0-9&]+", plain(name)) if len(w) > 3 and not w.isdigit() and w not in GENERIC}
    return {plain(ticker), *ALIASES.get(ticker, []), *words}


def _has_word(word: str, text: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])", text) is not None


def names_asset(ticker: str, name: str, mention: str, text: str) -> bool:
    """Whether `mention` really is in the text, and really names this asset."""
    mention = plain(mention).strip()
    if not mention or mention not in plain(text):
        return False
    return any(_has_word(w, mention) for w in names_for(ticker, name))


# "closes above $750", "finish week above", "hit (HIGH) $115", "up or down on November 3".
_PRICE_BET = re.compile(
    r"\b(close[sd]?|finish(es)?|open[sd]?)\b.*\b(above|below|at|over|under)\b|\bhits?\b.*\$"
    r"|\bdips?\b.*\$|\breach(es)?\b.*\$|\b(be|trade|stay)\b.*\b(above|below)\b.*\$|\bup or down\b|\(high\)|\(low\)",
    re.IGNORECASE,
)
_LOW_BET = re.compile(r"\(low\)|\bdips?\b", re.IGNORECASE)
_RANGE = re.compile(r"\bbetween\b.*\band\b", re.IGNORECASE)


def is_price_bet(title: str) -> bool:
    """A bet on where a price lands, not on something happening."""
    return bool(_PRICE_BET.search(title))


def check_market_impact(impact: TickerImpact, title: str, assets: dict[str, str]) -> TickerImpact | None:
    """The market's tag, corrected or dropped by what can be checked from its title."""
    target = impact.ticker
    if _RANGE.search(title):  # a bucket says nothing about which way: above it is a NO too
        impact = impact.model_copy(update={"direction": "unknown"})
    if factors.is_factor(target):
        if target not in factors.FACTORS:
            return None
        if is_price_bet(title):
            if target not in factors.PRICE_FACTORS:
                return None
            if _RANGE.search(title):
                return impact
            # "Oil hits (LOW) $60" pushes oil down, whatever the answer says.
            return impact.model_copy(update={"direction": "down" if _LOW_BET.search(title) else "up"})
        return impact
    if is_price_bet(title) or not names_asset(target, assets.get(target, ""), impact.mention, title):
        return None
    return impact


_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=get_settings().gemini_api_key)
    return _client


def tag_items(
    items: list[TagInput], holdings: dict[str, str] | None = None, universe: dict[str, str] | None = None,
) -> list[TaggedItem]:
    """Tag a batch of items of one kind, news or markets. Send ~20 per call.

    holdings: ticker -> description of the user's positions, so they can be tagged too.
    universe: ticker -> name of everything IOL offers.
    """
    holdings = holdings or {}
    universe = universe or {}
    if not items:
        return []
    kind = items[0].kind
    lines = [f"[{it.id}] {it.title}\n{it.text[:600]}" for it in items]
    try:
        response = _get_client().models.generate_content(
            model=get_settings().tagger_model,
            contents="\n\n".join(lines),
            config=types.GenerateContentConfig(
                system_instruction=_system(kind, holdings, universe),
                temperature=0,
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
    # Gemini sometimes garbles an id, which the database would refuse, losing the whole batch.
    sent = {it.id: it for it in items}
    batch.items = [item for item in batch.items if item.id in sent]
    # An item left out of a good answer had nothing to tag. Asking again would use up the quota and
    # hold up the queue, since those are always the first ones in it.
    answered = {item.id for item in batch.items}
    batch.items += [TaggedItem(id=i, summary="", impacts=[]) for i in sent if i not in answered]
    names = {t: "" for t in ALL_TICKERS} | {t: d for t, d in holdings.items()} | universe
    allowed = set(universe) or set(ALL_TICKERS)
    allowed |= set(holdings)
    dropped = 0
    for item in batch.items:
        source = sent[item.id]
        kept = []
        for impact in item.impacts:
            checked: TickerImpact | None
            if kind == "market":
                known = factors.is_factor(impact.ticker) or impact.ticker in allowed
                checked = check_market_impact(impact, source.title, names) if known else None
            else:
                ok = impact.ticker in allowed and names_asset(
                    impact.ticker, names.get(impact.ticker, ""), impact.mention, f"{source.title} {source.text}",
                )
                checked = impact if ok else None
            if checked:
                kept.append(checked)
            else:
                dropped += 1
        item.impacts = kept
    if dropped:
        log.info("dropped %d tags that didn't pass the checks", dropped)
    for item in batch.items:
        # Some answers come with HTML entities ("inversi&oacute;n").
        item.summary = html.unescape(item.summary)
        for impact in item.impacts:
            impact.reason = html.unescape(impact.reason)
    # Gemini sometimes writes "3" or "##" for an accented letter ("petr3leo", "econ##mico"). Those
    # items are left out, so they stay untagged and are tagged again on the next cycle.
    clean = [it for it in batch.items if not has_broken_accents(it)]
    if len(clean) < len(batch.items):
        log.warning("dropped %d tagged items with broken accents", len(batch.items) - len(clean))
    return clean


_BROKEN = re.compile(r"[A-Za-záéíóúñÁÉÍÓÚÑ](3|#+)[a-záéíóúñ]")


def has_broken_accents(item: TaggedItem) -> bool:
    return any(_BROKEN.search(text) for text in [item.summary, *(i.reason for i in item.impacts)])
