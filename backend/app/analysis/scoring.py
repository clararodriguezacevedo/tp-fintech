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

  score = 0.7 * tanh((news + markets) / 2) + 0.1 * trend + 0.1 * context + 0.1 * gap, in [-1, 1]

Broad "MERVAL" tags apply at half weight to every stock, "BONOS" tags to every bond.
Tickers the user holds can only get sell or keep; the rest can only get buy or keep.
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
W_EVIDENCE, W_TREND, W_CONTEXT, W_GAP = 0.7, 0.1, 0.1, 0.1
BUY_THRESHOLD, SELL_THRESHOLD = 0.3, -0.3
PRICED_IN_FULL = 1.5  # typical daily moves in the expected direction = fully priced in
SAME_STORY = 0.4  # title word overlap (Jaccard) above which two news items are one story
GAP_UNIT = 0.01  # a 1% premium versus usual counts as a strong gap signal
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


def _news_evidence(imp: TickerImpactRow, item: NewsRow, now: datetime) -> Evidence | None:
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
    return Evidence(
        kind="market", item_id=item.id, title=item.title, url=item.url, direction=imp.direction,
        strength=imp.strength, reason=imp.reason or "",
        contribution=round(sign * STRENGTH[imp.strength] * scaled, 4),
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
    """Close of the last session that had ended before `when`."""
    local = when.astimezone(market_hours.ART)
    done = [
        b for b in bars
        if b.day < local.date() or (b.day == local.date() and local.time() >= market_hours.CLOSE)
    ]
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
        spy = prices.daily_bars("SPY", market="nYSE")
        if spy:
            us = trend_score(spy, get_iol().quote("SPY", "nYSE").ultimo_precio or spy[-1].close)
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
            us_bars = prices.daily_bars(ticker, market="nYSE")
            ratios = [local[b.day] / b.close for b in us_bars if b.day in local and b.close > 0][-20:]
            us_now = get_iol().quote(ticker, "nYSE").ultimo_precio
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


def _combine(i: _Inputs, gap: float) -> Recommendation:
    evidence = i.own + [
        e.model_copy(update={"contribution": round(e.contribution * BROAD_WEIGHT, 4), "broad": True})
        for e in i.broad
    ]
    news = sum(e.contribution for e in evidence if e.kind == "news")
    markets = sum(e.contribution for e in evidence if e.kind == "market")
    evidence_part = W_EVIDENCE * math.tanh((news + markets) / 2)
    score = evidence_part + W_TREND * i.trend + W_CONTEXT * i.context + W_GAP * gap

    action: Action
    if i.held:
        action = "sell" if score <= SELL_THRESHOLD else "keep"
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
    }
    evidence.sort(key=lambda e: abs(e.contribution), reverse=True)
    return Recommendation(
        ticker=i.ticker, action=action, score=round(score, 4), confidence=round(confidence, 3),
        driver=max(parts, key=lambda k: parts[k]), held=i.held, price=i.price,
        breakdown=SignalBreakdown(
            news=round(news, 4), markets=round(markets, 4), trend=round(i.trend, 4),
            context=round(i.context, 4), gap=round(gap, 4),
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
    if "MERVAL" in signals:
        tickers |= stocks
    if "BONOS" in signals:
        tickers |= bonds

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
            bars = prices.daily_bars(ticker)
        except Exception:
            # IOL answers some bonds' history with a 500 (seen with TXMD9).
            log.warning("no history for %s", ticker)
        price: float | None = None
        try:
            price = get_iol().quote(ticker).ultimo_precio or None
        except Exception:
            log.warning("no live price for %s; using the last close", ticker)
        if not price and bars:
            price = bars[-1].close
        own = signals[ticker].evidence if ticker in signals else []
        if price:
            own = discount_priced_in(own, bars, price)
        inputs.append(_Inputs(
            ticker=ticker, held=ticker in holdings, price=price, own=own,
            broad=broad.evidence if broad else [],
            trend=trend_score(bars, price) if price else 0.0,
            context=context[group] if group else 0.0,
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
