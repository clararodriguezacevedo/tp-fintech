"""Turns tags, prices and the market into buy / sell / keep recommendations.

Per ticker:
  news     sum of direction * strength * recency decay, for news from the last 36 hours. The
           same story from several outlets counts once (titles grouped by word overlap).
  markets  sum of direction * strength * (24h probability move / 10 points), for every tagged
           market; a market that didn't move contributes nothing, however likely it is.
           Markets of the same event ("ceasefire through Oct 22 / 24 / 31") count once.
  priced in  each news item or market is discounted by how far the price already moved its
           way since it appeared, measured in the ticker's typical daily moves: after
           PRICED_IN_FULL typical days in the expected direction it no longer counts.
  trend    tanh of how many typical daily moves (ATR) the price sits from its 20-day average
  context  the trend of the whole market: Merval leaders for stocks, sovereign bonds for
           bonds, the S&P 500 (SPY in New York) for CEDEARs
  gap      CEDEARs only: how far the CEDEAR's price sits from its usual relation to the US
           share, after removing the move common to all CEDEARs (the dollar). Expensive
           versus usual -> expected to fall.
  macro    how unusual the 5-day change of riesgo país (bonds and banks; half for other local
           stocks; falling is good) or of the CCL dollar (CEDEARs; rising is good) is
  sector   news and markets about a sector peer (GGAL for the other banks) count at 30%

  concentration  buys only: when the portfolio already has more than 60% in the same risk
           group ("argentina": local stocks, bonds and Argentine CEDEARs like VIST; "exterior":
           the rest), 2 points off per point above 60% (at most 0.3).
           With only two groups one is always at 50% or more, so the bar is above that.

  score = 0.65 * tanh((news + markets) / 2) + 0.05 * trend + 0.1 * context + 0.1 * gap
          + 0.1 * macro + concentration

Market wrap-ups ("así cerró el mercado", "las acciones subieron hasta 6%") are ignored: they only
report moves that already happened. A news item tagged both for a ticker and for MERVAL/BONOS
counts once. Prediction markets resolving more than 6 months out weigh less.

Broad "MERVAL" tags apply at half weight to every stock, "BONOS" tags to every bond.
Tickers the user holds can only get sell (from -0.45, a higher bar than buying) or keep; the
rest can only get buy (from +0.3) or keep.
The weights are judgment calls until there is enough graded history to fit them
(scripts/fit_weights.py).
"""

import logging
import math
import re
import statistics
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel

from app import prices
from app.analysis import market_hours, risk
from app.analysis.tagger import UNIVERSE
from app.sources import corporate_events, macro
from app.brokers.iol import get_iol
from app.db import get_db, rows_as
from app.models.db import Action, Evidence, MarketRow, NewsRow, SignalBreakdown, TickerImpactRow
from app.models.iol import DailyBar
from app.portfolio import BOND_TYPES, EQUITY_TYPES, Holding, get_holdings

log = logging.getLogger(__name__)

STRENGTH = {"low": 0.33, "medium": 0.66, "high": 1.0}
NEWS_MAX_AGE_HOURS = 36
NEWS_HALF_LIFE_HOURS = 12
MARKET_MOVE_UNIT = 0.10  # a 10-point probability move counts like one "high" news item
MARKET_MOVE_CAP = 1.5
BROAD_WEIGHT = 0.5
# Trend got a low weight after scripts/backtest_trend.py found no next-day edge in it
# (49% right on 3,936 ticker-days, correlation +0.003).
W_EVIDENCE, W_TREND, W_CONTEXT, W_GAP, W_MACRO = 0.65, 0.05, 0.1, 0.1, 0.1
SECTOR_WEIGHT = 0.3  # news about a sector peer, versus news about the ticker itself
# Sectors whose shares tend to move together, each within one risk group.
SECTORS = {
    "bancos": ["GGAL", "BMA", "SUPV", "BBAR", "VALO", "BYMA"],
    "petróleo y gas": ["YPFD", "PAMP", "VIST", "TGSU2", "TGNO4"],
    "electricidad": ["EDN", "CEPU", "TRAN"],
    "materiales": ["TXAR", "ALUA", "LOMA"],
    "tecnología": ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META"],
}
SECTOR_OF = {t: name for name, members in SECTORS.items() for t in members}
BANKS = set(SECTORS["bancos"])
BUY_THRESHOLD = 0.3
PRICED_IN_FULL = 1.5  # typical daily moves in the expected direction = fully priced in
SAME_STORY = 0.4  # title word overlap (Jaccard) above which two news items are one story
GAP_UNIT = 0.01  # a 1% premium versus usual counts as a strong gap signal
FAR_MARKET_DAYS = 180  # prediction markets resolving later than this weigh less...
FAR_MARKET_MIN_WEIGHT = 0.25  # ...down to this share
SELL_THRESHOLD_HELD = -0.45  # selling something you hold needs more evidence than buying
CONCENTRATION_LIMIT = 0.60  # above this share of the portfolio in one risk group, buys in it are penalized
CONCENTRATION_PENALTY = 2.0  # score points per unit of share above the limit (70% -> -0.2)
CONCENTRATION_MAX = 0.3
MAX_EVIDENCE_SHOWN = 8
BROAD_TICKERS = ("MERVAL", "BONOS")
CEDEAR_TYPES = {"CEDEARS", "Cedears"}


@dataclass
class TickerSignals:
    evidence: list[Evidence] = field(default_factory=list)


def _fetch_by_ids[M: BaseModel](table: str, model: type[M], ids: list[str]) -> dict[str, M]:
    out: dict[str, M] = {}
    for i in range(0, len(ids), 100):
        rows = rows_as(model, get_db().table(table).select("*").in_("id", ids[i : i + 100]).execute().data)
        out.update({r.id: r for r in rows})  # type: ignore[attr-defined]
    return out


def _all_impacts() -> list[TickerImpactRow]:
    impacts: list[TickerImpactRow] = []
    page = 0
    while True:  # PostgREST returns at most 1000 rows per request
        batch = rows_as(
            TickerImpactRow,
            get_db().table("ticker_impacts").select("*").order("created_at", desc=True)
            .range(page * 1000, page * 1000 + 999).execute().data,
        )
        impacts += batch
        if len(batch) < 1000:
            return impacts
        page += 1


# Market wrap-ups only report moves that already happened: no new information.
_RECAP = re.compile(
    r"jornada financiera|as[ií] cerr[oó]|cierre (del|de) mercado|cierre de la (rueda|jornada)"
    r"|(acciones|bonos|adrs?|merval|s&p merval)( argentin[oa]s)? (rebot|sub|ca|baj|trep|se desplom)(aron|ieron|yeron|ó|i[oó]|y[oó])\b"
    r"|(acciones|bonos|adrs?|merval|s&p merval)( argentin[oa]s)? (cotiz|oper|cerr|termin)(aron|[oó]) en (alza|baja|rojo|verde|positivo|negativo)"
    r"|riesgo pa[ií]s (sube|baja|subi[oó]|baj[oó]) .*(hoy|en la jornada)"
    r"|stocks? (rose|fell|rallied|slid|closed)|stock market today|markets? wrap",
    re.IGNORECASE,
)


def is_market_recap(title: str) -> bool:
    return bool(_RECAP.search(title))


def _news_evidence(imp: TickerImpactRow, item: NewsRow, now: datetime) -> Evidence | None:
    if is_market_recap(item.title):
        return None
    published = item.published_at or item.created_at
    age_h = (now - published).total_seconds() / 3600
    if age_h > NEWS_MAX_AGE_HOURS:
        return None
    sign = 1 if imp.direction == "up" else -1
    contribution = sign * STRENGTH[imp.strength] * 0.5 ** (max(age_h, 0) / NEWS_HALF_LIFE_HOURS)
    return Evidence(
        kind="news", item_id=item.id, title=item.title, url=item.url, direction=imp.direction,
        strength=imp.strength, reason=imp.reason or "", contribution=round(contribution, 4),
        detail=f"hace {age_h:.0f} h", since=published,
    )


def _market_evidence(imp: TickerImpactRow, item: MarketRow, now: datetime) -> Evidence | None:
    if item.change_24h is None:
        return None
    sign = 1 if imp.direction == "up" else -1
    scaled = max(-MARKET_MOVE_CAP, min(MARKET_MOVE_CAP, item.change_24h / MARKET_MOVE_UNIT))
    prob = f"{item.probability * 100:.0f}% " if item.probability is not None else ""
    # A market resolving years from now says little about tomorrow: weight falls past 6 months.
    horizon = 1.0
    if item.end_date:
        days_left = (item.end_date - now).days
        if days_left > FAR_MARKET_DAYS:
            horizon = max(FAR_MARKET_MIN_WEIGHT, FAR_MARKET_DAYS / days_left)
    return Evidence(
        kind="market", item_id=item.id, title=item.title, url=item.url, direction=imp.direction,
        strength=imp.strength, reason=imp.reason or "",
        contribution=round(sign * STRENGTH[imp.strength] * scaled * horizon, 4),
        detail=f"{item.source}: {prob}({item.change_24h * 100:+.1f} pts en 24 h)".replace(".", ","),
        since=now - timedelta(hours=24),
    )


# Same story from several outlets

_STOP = set(
    "para como sobre desde entre hasta pero porque cuando donde este esta estos estas todo todos "
    "with from that this have will their about after into over says said than more".split()
)


def _words(title: str) -> set[str]:
    plain = unicodedata.normalize("NFKD", title.lower()).encode("ascii", "ignore").decode()
    return {w for w in re.findall(r"[a-z0-9]+", plain) if len(w) > 3 and w not in _STOP}


def group_same_story(evidence: list[Evidence]) -> list[Evidence]:
    """Keep the strongest news item of each story; markets pass through untouched."""
    news = sorted((e for e in evidence if e.kind == "news"), key=lambda e: -abs(e.contribution))
    stories: list[tuple[set[str], Evidence]] = []
    for e in news:
        words = _words(e.title)
        for i, (seen, rep) in enumerate(stories):
            overlap = len(words & seen) / max(len(words | seen), 1)
            if overlap >= SAME_STORY:
                stories[i] = (seen | words, rep.model_copy(update={"sources": rep.sources + 1}))
                break
        else:
            stories.append((words, e))
    return [rep for _, rep in stories] + [e for e in evidence if e.kind == "market"]


def collect_signals(now: datetime | None = None) -> dict[str, TickerSignals]:
    """Evidence per tagged ticker (including the broad MERVAL and BONOS pseudo-tickers)."""
    now = now or datetime.now(timezone.utc)
    impacts = _all_impacts()
    news = _fetch_by_ids(
        "news_items", NewsRow, list({i.item_id for i in impacts if i.item_kind == "news"})
    )
    markets = _fetch_by_ids(
        "prediction_markets", MarketRow, list({i.item_id for i in impacts if i.item_kind == "market"})
    )

    signals: dict[str, TickerSignals] = {}
    # Strongest market evidence per (ticker, event), so one event counts once.
    by_event: dict[tuple[str, str], Evidence] = {}
    for imp in impacts:
        if imp.item_kind == "news":
            n = news.get(imp.item_id)
            ev = _news_evidence(imp, n, now) if n else None
            if ev and abs(ev.contribution) > 1e-4:
                signals.setdefault(imp.ticker, TickerSignals()).evidence.append(ev)
        else:
            m = markets.get(imp.item_id)
            ev = _market_evidence(imp, m, now) if m else None
            if not m or not ev or abs(ev.contribution) <= 1e-4:
                continue
            key = (imp.ticker, m.event_key or m.id)
            if key not in by_event or abs(ev.contribution) > abs(by_event[key].contribution):
                by_event[key] = ev

    for (ticker, _), ev in by_event.items():
        signals.setdefault(ticker, TickerSignals()).evidence.append(ev)
    for s in signals.values():
        s.evidence = group_same_story(s.evidence)
    return signals


# Prices

def _atr_pct(bars: list[DailyBar], price: float) -> float | None:
    if len(bars) < 15 or price <= 0:
        return None
    atr = risk.atr([b.high for b in bars], [b.low for b in bars], [b.close for b in bars])
    return atr / price if atr > 0 else None


def trend_score(bars: list[DailyBar], last: float) -> float:
    """tanh(z / 2) where z is how many ATRs `last` sits from the 20-day average close."""
    bars = [b for b in bars if b.close > 0]
    if len(bars) < 21:
        return 0.0
    closes = [b.close for b in bars]
    atr = risk.atr([b.high for b in bars], [b.low for b in bars], closes)
    if atr <= 0:
        return 0.0
    return math.tanh((last - sum(closes[-20:]) / 20) / atr / 2)


def _close_before(bars: list[DailyBar], when: datetime) -> float | None:
    """Reference price for "already in the price": the close before the session `when` falls in.

    A note published during or after a trading day (often an after-close wrap-up) may describe
    that day's whole move, so the reference is the previous day's close, not that day's. Before
    the open, or on a day without trading, it is simply the last close.
    """
    local = when.astimezone(market_hours.ART)
    traded_today = local.weekday() < 5 and local.time() >= market_hours.OPEN
    done = [b for b in bars if b.day < local.date() or (b.day == local.date() and not traded_today)]
    return done[-1].close if done else None


def discount_priced_in(evidence: list[Evidence], bars: list[DailyBar], price: float) -> list[Evidence]:
    """Shrink each item by how far the price already moved its way since it appeared."""
    atr_pct = _atr_pct(bars, price)
    if atr_pct is None:
        return evidence
    out = []
    for e in evidence:
        ref = _close_before(bars, e.since) if e.since else None
        if not ref:
            out.append(e)
            continue
        move = price / ref - 1
        same_way = (move / atr_pct) * (1 if e.contribution >= 0 else -1)
        priced = max(0.0, min(1.0, same_way / PRICED_IN_FULL))
        out.append(e.model_copy(update={
            "contribution": round(e.contribution * (1 - priced), 4),
            "move_since": round(move, 4),
            "priced_in": round(priced, 2),
        }))
    return out


def market_context() -> dict[str, float]:
    """Trend of the whole market per group: Merval leaders, sovereign bonds and the S&P 500."""
    def median_trend(tickers: list[str]) -> float:
        values = []
        for t in tickers:
            try:
                bars = prices.daily_bars(t)
                if bars:
                    values.append(trend_score(bars, bars[-1].close))
            except Exception:
                log.warning("no history for %s in market context", t)
        return statistics.median(values) if values else 0.0

    us = 0.0
    try:
        spy = prices.daily_bars("SPY", market="US")
        if spy:
            us = trend_score(spy, get_iol().quote("SPY", "US").price or spy[-1].close)
    except Exception:
        log.warning("no S&P 500 data for market context")
    return {
        "stocks": median_trend(UNIVERSE["acciones"]),
        "bonds": median_trend(UNIVERSE["bonos"]),
        "us": us,
    }


def cedear_gaps(local_prices: dict[str, float]) -> dict[str, float]:
    """Gap signal per CEDEAR: -tanh(premium versus its usual relation to the US share, after
    removing the median premium of all CEDEARs, which is the dollar's move)."""
    premiums: dict[str, float] = {}
    for ticker, price in local_prices.items():
        try:
            local = {b.day: b.close for b in prices.daily_bars(ticker) if b.close > 0}
            us_bars = prices.daily_bars(ticker, market="US")
            ratios = [local[b.day] / b.close for b in us_bars if b.day in local and b.close > 0][-20:]
            us_now = get_iol().quote(ticker, "US").price
            if len(ratios) < 10 or not us_now:
                continue
            premiums[ticker] = (price / us_now) / statistics.median(ratios) - 1
        except Exception:
            log.warning("no US data for CEDEAR %s", ticker)
    if len(premiums) < 3:
        return {}
    common = statistics.median(premiums.values())
    return {t: -math.tanh((p - common) / GAP_UNIT) for t, p in premiums.items()}


# Scoring

class Recommendation(BaseModel):
    ticker: str
    action: Action
    score: float
    confidence: float
    driver: str
    held: bool
    price: float | None
    breakdown: SignalBreakdown
    evidence: list[Evidence]


@dataclass
class _Inputs:
    ticker: str
    held: bool
    price: float | None
    own: list[Evidence]
    broad: list[Evidence]
    trend: float
    context: float
    risk_group: str | None = None
    group_share: float | None = None
    change_3m: float | None = None
    from_high: float | None = None
    sector: list[Evidence] = field(default_factory=list)
    macro: float = 0.0
    macro_source: str | None = None
    macro_level: float | None = None
    macro_change: float | None = None
    event: corporate_events.CorporateEvent | None = None


def sector_evidence(ticker: str, signals: dict[str, TickerSignals]) -> list[Evidence]:
    """Evidence about the ticker's sector peers, strongest per item, tagged with the peer."""
    sector = SECTOR_OF.get(ticker)
    if not sector:
        return []
    best: dict[str, Evidence] = {}
    for peer in SECTORS[sector]:
        if peer == ticker or peer not in signals:
            continue
        for e in signals[peer].evidence:
            if e.item_id not in best or abs(e.contribution) > abs(best[e.item_id].contribution):
                best[e.item_id] = e.model_copy(update={"via": peer})
    return list(best.values())


def macro_for(ticker: str, group: str | None, signals: dict[str, macro.MacroSignal]) -> tuple[float, str | None]:
    """(signal, source): riesgo país falling is good for bonds and banks (half for the other
    local stocks); the CCL rising is good for CEDEARs, priced in pesos."""
    if group == "us" and ticker not in ARGENTINE_CEDEARS:
        s = signals.get("ccl")
        return (s.signal, "ccl") if s else (0.0, None)
    if group in ("bonds", "stocks") or ticker in ARGENTINE_CEDEARS:
        s = signals.get("riesgo_pais")
        if not s:
            return 0.0, None
        weight = 1.0 if group == "bonds" or ticker in BANKS else 0.5
        return -s.signal * weight, "riesgo_pais"
    return 0.0, None


# Argentine companies listed abroad: their CEDEARs carry Argentine risk, not foreign.
ARGENTINE_CEDEARS = {"VIST"}


def risk_group(ticker: str, stocks: set[str], bonds: set[str]) -> str:
    return "argentina" if ticker in stocks or ticker in bonds or ticker in ARGENTINE_CEDEARS else "exterior"


def concentration_penalty(share: float | None) -> float:
    if share is None or share <= CONCENTRATION_LIMIT:
        return 0.0
    return -min(CONCENTRATION_MAX, CONCENTRATION_PENALTY * (share - CONCENTRATION_LIMIT))


def three_month_context(bars: list[DailyBar], price: float) -> tuple[float | None, float | None]:
    """(change over ~3 months, distance from the 3-month high), shown next to a signal."""
    window = [b for b in bars if b.close > 0][-63:]
    if len(window) < 40 or price <= 0:
        return None, None
    high = max(max(b.high for b in window), price)
    return price / window[0].close - 1, price / high - 1


def _combine(i: _Inputs, gap: float) -> Recommendation:
    # A news item tagged for this ticker, for the whole market or for a peer counts once,
    # at the weight of the most direct tag.
    seen = {e.item_id for e in i.own}
    broad = [
        e.model_copy(update={"contribution": round(e.contribution * BROAD_WEIGHT, 4), "broad": True})
        for e in i.broad if e.item_id not in seen
    ]
    seen |= {e.item_id for e in broad}
    sector = [
        e.model_copy(update={"contribution": round(e.contribution * SECTOR_WEIGHT, 4)})
        for e in i.sector if e.item_id not in seen
    ]
    evidence = i.own + broad + sector
    news = sum(e.contribution for e in evidence if e.kind == "news")
    markets = sum(e.contribution for e in evidence if e.kind == "market")
    evidence_part = W_EVIDENCE * math.tanh((news + markets) / 2)
    # Buying more of a risk the portfolio is already heavy in needs a stronger case.
    concentration = 0.0 if i.held else concentration_penalty(i.group_share)
    score = (
        evidence_part + W_TREND * i.trend + W_CONTEXT * i.context + W_GAP * gap + W_MACRO * i.macro
        + concentration
    )

    action: Action
    if i.held:
        action = "sell" if score <= SELL_THRESHOLD_HELD else "keep"
    else:
        action = "buy" if score >= BUY_THRESHOLD else "keep"

    # More independent pieces of evidence, more confidence; trend alone never gets far.
    coverage = 1 - math.exp(-(len(evidence) + 1) / 3)
    confidence = min(1.0, abs(score) / 0.8) * coverage
    total = abs(news) + abs(markets) or 1
    parts = {
        "news": abs(evidence_part) * abs(news) / total,
        "markets": abs(evidence_part) * abs(markets) / total,
        "trend": W_TREND * abs(i.trend),
        "context": W_CONTEXT * abs(i.context),
        "gap": W_GAP * abs(gap),
        "macro": W_MACRO * abs(i.macro),
    }
    evidence.sort(key=lambda e: abs(e.contribution), reverse=True)
    return Recommendation(
        ticker=i.ticker, action=action, score=round(score, 4), confidence=round(confidence, 3),
        driver=max(parts, key=lambda k: parts[k]), held=i.held, price=i.price,
        breakdown=SignalBreakdown(
            news=round(news, 4), markets=round(markets, 4), trend=round(i.trend, 4),
            context=round(i.context, 4), gap=round(gap, 4), concentration=round(concentration, 4),
            risk_group=i.risk_group,
            group_share=round(i.group_share, 4) if i.group_share is not None else None,
            change_3m=round(i.change_3m, 4) if i.change_3m is not None else None,
            from_high=round(i.from_high, 4) if i.from_high is not None else None,
            macro=round(i.macro, 4), macro_source=i.macro_source,  # type: ignore[arg-type]
            macro_level=i.macro_level,
            macro_change=round(i.macro_change, 4) if i.macro_change is not None else None,
            event_kind=i.event.kind if i.event else None,  # type: ignore[arg-type]
            event_date=i.event.ex_date if i.event else None,
            event_yield=round(i.event.yield_, 5) if i.event and i.event.yield_ is not None else None,
        ),
        evidence=evidence[:MAX_EVIDENCE_SHOWN],
    )


def score_all(kind: str = "live", now: datetime | None = None) -> list[Recommendation]:
    """Score every ticker with evidence plus every holding, and save the results.

    kind="live": refreshed each cycle, one row per ticker and target day.
    kind="daily": run after the close; graded on the next day.
    """
    signals = collect_signals(now)
    holdings: dict[str, Holding]
    try:
        holdings = {h.ticker: h for h in get_holdings()}
    except Exception:
        log.exception("could not load holdings; scoring without portfolio")
        holdings = {}

    stocks = set(UNIVERSE["acciones"]) | {t for t, h in holdings.items() if h.type in EQUITY_TYPES}
    bonds = set(UNIVERSE["bonos"]) | {t for t, h in holdings.items() if h.type in BOND_TYPES}
    cedears = set(UNIVERSE["cedears"]) | {t for t, h in holdings.items() if h.type in CEDEAR_TYPES}
    tickers = {t for t in signals if t not in BROAD_TICKERS} | set(holdings)
    # Peers of a ticker with news get scored too, so the news can spread to them.
    tickers |= {p for t in list(tickers) if t in SECTOR_OF for p in SECTORS[SECTOR_OF[t]]}
    if "MERVAL" in signals:
        tickers |= stocks
    if "BONOS" in signals:
        tickers |= bonds

    # Share of the portfolio in each risk group (positions valued in pesos).
    peso_holdings = [h for h in holdings.values() if h.currency == "ARS"]
    total_value = sum(h.value for h in peso_holdings)
    group_shares: dict[str, float] = {}
    for h in peso_holdings:
        g = risk_group(h.ticker, stocks, bonds)
        group_shares[g] = group_shares.get(g, 0.0) + h.value / total_value

    try:
        macro_signals = macro.fetch()
    except Exception:
        log.exception("macro data failed; left at 0")
        macro_signals = {}
    try:
        events = corporate_events.upcoming(market_hours.now_art().date())
    except Exception:
        log.exception("could not load corporate events")
        events = {}

    try:
        context = market_context()
    except Exception:
        log.exception("market context failed; left at 0")
        context = {"stocks": 0.0, "bonds": 0.0, "us": 0.0}

    inputs: list[_Inputs] = []
    for ticker in sorted(tickers):
        group = "stocks" if ticker in stocks else "bonds" if ticker in bonds else "us" if ticker in cedears else None
        broad = signals.get("MERVAL") if group == "stocks" else signals.get("BONOS") if group == "bonds" else None
        bars: list[DailyBar] = []
        try:
            bars = prices.daily_bars(ticker, days=100)
        except Exception:
            # IOL answers some bonds' history with a 500 (seen with TXMD9).
            log.warning("no history for %s", ticker)
        price: float | None = None
        try:
            price = get_iol().quote(ticker).price or None
        except Exception:
            log.warning("no live price for %s; using the last close", ticker)
        if not price and bars:
            price = bars[-1].close
        own = signals[ticker].evidence if ticker in signals else []
        broad_ev = broad.evidence if broad else []
        peers = sector_evidence(ticker, signals)
        if price:
            own = discount_priced_in(own, bars, price)
            broad_ev = discount_priced_in(broad_ev, bars, price)
            peers = discount_priced_in(peers, bars, price)
        macro_value, macro_source = macro_for(ticker, group, macro_signals)
        ms = macro_signals.get(macro_source) if macro_source else None
        change_3m, from_high = three_month_context(bars, price) if price else (None, None)
        rg = risk_group(ticker, stocks, bonds)
        inputs.append(_Inputs(
            ticker=ticker, held=ticker in holdings, price=price, own=own,
            broad=broad_ev, sector=peers,
            trend=trend_score(bars, price) if price else 0.0,
            context=context[group] if group else 0.0,
            risk_group=rg, group_share=group_shares.get(rg, 0.0) if total_value else None,
            change_3m=change_3m, from_high=from_high,
            macro=macro_value, macro_source=macro_source,
            macro_level=ms.level if ms else None, macro_change=ms.change if ms else None,
            event=events.get(ticker),
        ))

    gaps = cedear_gaps({i.ticker: i.price for i in inputs if i.ticker in cedears and i.price})
    recs = [_combine(i, gaps.get(i.ticker, 0.0)) for i in inputs]

    if recs:
        target = market_hours.next_close_date(now)
        rows = [{
            "ticker": r.ticker,
            "action": r.action,
            "score": r.score,
            "confidence": r.confidence,
            "driver": r.driver,
            "held": r.held,
            "price_at_rec": r.price,
            "signal_breakdown": r.breakdown.model_dump(),
            "evidence": [e.model_dump(mode="json") for e in r.evidence],
            "target_date": target.isoformat(),
            "kind": kind,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        } for r in recs]
        get_db().table("recommendations").upsert(rows, on_conflict="ticker,target_date,kind").execute()
        log.info("scored %d tickers (%s) for %s", len(recs), kind, target)
    return recs
