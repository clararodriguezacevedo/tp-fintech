"""Turns tags and price trend into buy / sell / keep recommendations.

Per ticker:
  news     sum of direction * strength * recency decay, for news from the last 36 hours
  markets  sum of direction * strength * (24h probability move / 10 points), for every tagged
           market; a market that didn't move contributes nothing, however likely it is.
           Markets of the same event ("ceasefire through Oct 22 / 24 / 31") count once, using
           the one with the strongest contribution.
  trend    tanh of how many ATRs the price sits above or below its 20-day average

  score = 0.7 * tanh((news + markets) / 2) + 0.3 * trend, in [-1, 1]

Broad "MERVAL" tags apply at half weight to every stock, "BONOS" tags to every bond.
Tickers the user holds can only get sell or keep; the rest can only get buy or keep.
"""

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone

from pydantic import BaseModel

from app.analysis import market_hours, risk
from app.analysis.tagger import UNIVERSE
from app.brokers.iol import get_iol
from app.db import get_db, rows_as
from app.models.db import Action, Evidence, MarketRow, NewsRow, SignalBreakdown, TickerImpactRow
from app import prices
from app.portfolio import BOND_TYPES, EQUITY_TYPES, Holding, get_holdings

log = logging.getLogger(__name__)

STRENGTH = {"low": 0.33, "medium": 0.66, "high": 1.0}
NEWS_MAX_AGE_HOURS = 36
NEWS_HALF_LIFE_HOURS = 12
MARKET_MOVE_UNIT = 0.10  # a 10-point probability move counts like one "high" news item
MARKET_MOVE_CAP = 1.5
BROAD_WEIGHT = 0.5
EVIDENCE_WEIGHT, TREND_WEIGHT = 0.7, 0.3
BUY_THRESHOLD, SELL_THRESHOLD = 0.3, -0.3
MAX_EVIDENCE_SHOWN = 8
BROAD_TICKERS = ("MERVAL", "BONOS")


@dataclass
class TickerSignals:
    news: float = 0.0
    markets: float = 0.0
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
        detail=f"hace {age_h:.0f} h",
    )


def _market_evidence(imp: TickerImpactRow, item: MarketRow) -> Evidence | None:
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
    )


def collect_signals(now: datetime | None = None) -> dict[str, TickerSignals]:
    """Signals per tagged ticker (including the broad MERVAL and BONOS pseudo-tickers)."""
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
                s = signals.setdefault(imp.ticker, TickerSignals())
                s.news += ev.contribution
                s.evidence.append(ev)
        else:
            m = markets.get(imp.item_id)
            ev = _market_evidence(imp, m) if m else None
            if not m or not ev or abs(ev.contribution) <= 1e-4:
                continue
            key = (imp.ticker, m.event_key or m.id)
            if key not in by_event or abs(ev.contribution) > abs(by_event[key].contribution):
                by_event[key] = ev

    for (ticker, _), ev in by_event.items():
        s = signals.setdefault(ticker, TickerSignals())
        s.markets += ev.contribution
        s.evidence.append(ev)
    return signals


# Prices

def trend_score(ticker: str, last: float) -> float:
    """tanh(z / 2) where z is how many ATRs `last` sits from the 20-day average close."""
    bars = prices.daily_bars(ticker)
    if len(bars) < 21:
        return 0.0
    closes = [b.close for b in bars]
    atr = risk.atr([b.high for b in bars], [b.low for b in bars], closes)
    if atr <= 0:
        return 0.0
    sma20 = sum(closes[-20:]) / 20
    return math.tanh((last - sma20) / atr / 2)


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


def _combine(
    ticker: str, own: TickerSignals | None, broad: TickerSignals | None, trend: float,
    held: bool, price: float | None,
) -> Recommendation:
    news = (own.news if own else 0) + BROAD_WEIGHT * (broad.news if broad else 0)
    markets = (own.markets if own else 0) + BROAD_WEIGHT * (broad.markets if broad else 0)
    evidence = (own.evidence if own else []) + [
        e.model_copy(update={"contribution": round(e.contribution * BROAD_WEIGHT, 4), "broad": True})
        for e in (broad.evidence if broad else [])
    ]
    score = EVIDENCE_WEIGHT * math.tanh((news + markets) / 2) + TREND_WEIGHT * trend

    action: Action
    if held:
        action = "sell" if score <= SELL_THRESHOLD else "keep"
    else:
        action = "buy" if score >= BUY_THRESHOLD else "keep"

    # More independent pieces of evidence, more confidence; trend alone never gets far.
    coverage = 1 - math.exp(-(len(evidence) + 1) / 3)
    confidence = min(1.0, abs(score) / 0.8) * coverage
    weights = {"news": abs(news), "markets": abs(markets), "trend": abs(trend) * 2}
    driver = max(weights, key=lambda k: weights[k])
    evidence.sort(key=lambda e: abs(e.contribution), reverse=True)
    return Recommendation(
        ticker=ticker, action=action, score=round(score, 4), confidence=round(confidence, 3),
        driver=driver, held=held, price=price,
        breakdown=SignalBreakdown(news=round(news, 4), markets=round(markets, 4), trend=round(trend, 4)),
        evidence=evidence[:MAX_EVIDENCE_SHOWN],
    )


def score_all(kind: str = "live", now: datetime | None = None) -> list[Recommendation]:
    """Score every ticker with evidence plus every holding, and save the results.

    kind="live": refreshed each cycle, one row per ticker and target day.
    kind="daily": run after the close; priced at the close and graded the next day.
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
    tickers = {t for t in signals if t not in BROAD_TICKERS} | set(holdings)
    if "MERVAL" in signals:
        tickers |= stocks
    if "BONOS" in signals:
        tickers |= bonds

    target = market_hours.next_close_date(now)
    recs = []
    for ticker in sorted(tickers):
        broad = (
            signals.get("MERVAL") if ticker in stocks
            else signals.get("BONOS") if ticker in bonds else None
        )
        price: float | None = None
        trend = 0.0
        try:
            price = get_iol().quote(ticker).ultimo_precio or None
        except Exception:
            log.warning("no price for %s", ticker)
        if price:
            try:
                trend = trend_score(ticker, price)
            except Exception:
                # IOL answers some bonds' history with a 500 (seen with TXMD9).
                log.warning("no history for %s; trend left at 0", ticker)
        recs.append(_combine(ticker, signals.get(ticker), broad, trend, ticker in holdings, price))

    if recs:
        rows = [{
            "ticker": r.ticker,
            "action": r.action,
            "score": r.score,
            "confidence": r.confidence,
            "driver": r.driver,
            "held": r.held,
            "price_at_rec": r.price,
            "signal_breakdown": r.breakdown.model_dump(),
            "evidence": [e.model_dump() for e in r.evidence],
            "target_date": target.isoformat(),
            "kind": kind,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        } for r in recs]
        get_db().table("recommendations").upsert(rows, on_conflict="ticker,target_date,kind").execute()
    log.info("scored %d tickers (%s) for %s", len(recs), kind, target)
    return recs
