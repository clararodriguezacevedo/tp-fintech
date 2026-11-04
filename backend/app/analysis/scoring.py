"""Turns tags and prediction markets into buy / sell / keep recommendations.

Every piece of evidence about a ticker has a value (-1 to +1) and a weight:

  news     value +1 good, -1 bad, 0 unclear. Weight 1 until a BYMA open could trade on it, half after
           one open, nothing after two: nights, weekends and holidays don't age it.
  market   value = its 24h probability move, beyond what the clock explains, over MARKET_MOVE_UNIT
           (at most 1), with the sign of what YES does. Weight 1, FACTOR_WEIGHT if it reaches the
           ticker through a factor (app.analysis.factors), less if it resolves far away.

  score = sum(weight * value) / (sum(weight) + PRIOR_WEIGHT)

An average, so ten items saying the same aren't worth ten times one; PRIOR_WEIGHT is a neutral vote
that makes one item count less than several. Between -1 and +1, and 0 without evidence.

Then, per asset class (shares, CEDEARs, bonds), tickers with evidence are ranked by score (equal
scores share their place):

  buy   not held, in the top TOP_SHARE of its class, score >= BUY_THRESHOLD, within the profile
  sell  held, score <= SELL_THRESHOLD_HELD (selling costs commissions and undoes a choice)
  keep  everything else

Not news: a repeat of what was already published about the ticker in the last NOVELTY_DAYS (it
counts once, looking only backwards), and market wrap-ups. A market only counts with enough volume,
a move above the noise and at least MIN_MARKET_DAYS left. Markets of the same event count once: the
most traded one.

Riesgo país and the CCL dollar (macro) are measured next to the score, but don't enter it.
"""

import logging
import math
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from pydantic import BaseModel

from app import prices, universe
from app.analysis import factors, market_hours, suitability
from app.assets import asset_types
from app.brokers.iol import get_iol
from app.db import get_db, rows_as
from app.models.db import Action, Evidence, MarketRow, NewsRow, RecommendationRow, SignalBreakdown, TickerImpactRow
from app.models.iol import DailyBar
from app.portfolio import BOND_TYPES, EQUITY_TYPES, Holding, get_holdings
from app.schemas import MarketCase
from app.sources import corporate_events, macro

log = logging.getLogger(__name__)

MODEL_VERSION = 2  # saved with every recommendation: change it when the model changes
TAG_VERSION = 2  # the tags this model reads (ticker_impacts.tag_version)

PRIOR_WEIGHT = 1.0
TOP_SHARE = 0.2
BUY_THRESHOLD = 0.35  # one market through a factor (0.33 at most) isn't enough to buy; two are
SELL_THRESHOLD_HELD = -0.6  # a single bad headline (-0.5) isn't enough to sell
NEWS_MAX_OPENS = 2  # opens after which a news item stops counting; each one halves its weight
NOVELTY_DAYS = 7  # calendar days looked back for repeats, 5 sessions
NOVELTY_SIMILARITY = 0.4  # word overlap (cosine) of title and summary from which it's the same story
LOOKBACK_DAYS = 10  # tags read per cycle

MARKET_MOVE_UNIT = 0.10  # a 10-point probability move is a full value
MARKET_MIN_MOVE = 0.02  # less than this is noise
MARKET_MIN_VOLUME = 1000.0  # dollars traded in 24 hours: below this a move says little
MIN_MARKET_DAYS = 3  # markets resolving sooner move by the clock, not by news
FAR_MARKET_DAYS = 180  # prediction markets resolving later than this weigh less...
FAR_MARKET_MIN_WEIGHT = 0.25  # ...down to this share
FACTOR_WEIGHT = 0.5  # a market reaching the ticker through a factor, versus one naming it

CONCENTRATION_LIMIT = 0.60  # of the portfolio in one risk group: buys stop there (app.analysis.risk)
MAX_SCORED = 100  # tickers scored per cycle (the universe has ~600)
BANKS = {"GGAL", "BMA", "SUPV", "BBAR", "VALO", "BYMA"}
CEDEAR_TYPES = {"CEDEARS", "Cedears"}

# What the first model (version 1) asked for, to replay its old recommendations in the simulation.
V1_BUY, V1_SELL = 0.3, -0.45


def _fetch_by_ids[M: BaseModel](table: str, model: type[M], ids: list[str]) -> dict[str, M]:
    out: dict[str, M] = {}
    for i in range(0, len(ids), 100):
        rows = rows_as(model, get_db().table(table).select("*").in_("id", ids[i : i + 100]).execute().data)
        out.update({r.id: r for r in rows})  # type: ignore[attr-defined]
    return out


def _recent_impacts(now: datetime) -> list[TickerImpactRow]:
    start = (now - timedelta(days=LOOKBACK_DAYS)).isoformat()
    impacts: list[TickerImpactRow] = []
    page = 0
    while True:  # PostgREST returns at most 1000 rows per request
        batch = rows_as(
            TickerImpactRow,
            get_db().table("ticker_impacts").select("*").eq("tag_version", TAG_VERSION).gte("created_at", start)
            .order("created_at", desc=True).range(page * 1000, page * 1000 + 999).execute().data,
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
    opens = market_hours.opens_between(published, now)
    if opens >= NEWS_MAX_OPENS:
        return None
    value = {"up": 1.0, "down": -1.0, "unknown": 0.0}[imp.direction]
    weight = 0.5**opens
    return Evidence(
        kind="news", item_id=item.id, title=item.title, url=item.url, direction=imp.direction,
        reason=imp.reason or "", value=value, weight=weight, contribution=round(value * weight, 4),
        detail="ya hubo una apertura" if opens else "todavía sin operar", since=published,
    )


# "Happens by a date" markets: the chance shrinks as days pass without it happening. Not "above
# X at the end of 2027" or "by market cap", which are measured once.
_MONTH = r"(jan(uary)?|feb(ruary)?|mar(ch)?|apr(il)?|may|june?|july?|aug(ust)?|sep(t(ember)?)?|oct(ober)?|nov(ember)?|dec(ember)?)"
_DEADLINE = re.compile(
    rf"\b(hits?|reach(es)?|dips?)\b|\bbefore\b|\bby\s+(the\s+)?(end\b|{_MONTH}\b|\d)",
    re.IGNORECASE,
)


def is_deadline_market(title: str) -> bool:
    return bool(_DEADLINE.search(title))


def time_decay(probability: float, change_24h: float, days_left: float) -> float:
    """How much a deadline market's probability should have moved in 24 hours (<= 0) just from
    the day passing, if the chance of it happening stays the same each day.

    A probability p with d days to go means a daily hazard h with p = 1 - exp(-h * d); with one
    day less and no news, it becomes 1 - exp(-h * (d - 1)).
    """
    before = probability - change_24h
    if not 0 < before < 1 or days_left <= 0:
        return 0.0
    hazard = -math.log(1 - before) / (days_left + 1)
    return (1 - math.exp(-hazard * days_left)) - before


def _market_evidence(imp: TickerImpactRow, item: MarketRow, now: datetime) -> Evidence | None:
    if item.change_24h is None or imp.direction == "unknown":
        return None
    if (item.volume_24h or 0) < MARKET_MIN_VOLUME:
        return None
    # A market resolving years from now says little about tomorrow: weight falls past 6 months.
    horizon = 1.0
    if item.end_date:
        days_left = (item.end_date - now).days
        if days_left < MIN_MARKET_DAYS:
            return None
        if days_left > FAR_MARKET_DAYS:
            horizon = max(FAR_MARKET_MIN_WEIGHT, FAR_MARKET_DAYS / days_left)
    decay = 0.0
    if item.end_date and item.probability is not None and is_deadline_market(item.title):
        decay = time_decay(item.probability, item.change_24h, (item.end_date - now).total_seconds() / 86400)
    move = item.change_24h - decay
    # A fall smaller than the clock explains isn't news, in either direction.
    if item.change_24h < 0 <= move or abs(move) < MARKET_MIN_MOVE:
        return None
    sign = 1 if imp.direction == "up" else -1
    value = sign * max(-1.0, min(1.0, move / MARKET_MOVE_UNIT))
    prob = f"{item.probability * 100:.0f}% " if item.probability is not None else ""
    clock = f", {decay * 100:+.1f} por el paso del tiempo" if abs(decay) >= 0.005 else ""
    return Evidence(
        kind="market", item_id=item.id, title=item.title, url=item.url, direction=imp.direction,
        reason=imp.reason or "", value=round(value, 4), weight=horizon, contribution=round(value * horizon, 4),
        detail=f"{item.source}: {prob}({item.change_24h * 100:+.1f} pts en 24 h{clock})".replace(".", ","),
        since=now - timedelta(hours=24),
    )


def market_cases() -> list[MarketCase]:
    """What the scoring does with typical moves of a market, by running it, to explain it on the
    site: YES can be good or bad for the ticker, and its probability can rise or fall."""
    now = datetime.now(timezone.utc)
    deadline = now + timedelta(days=5)
    rows = [
        ("up", 0.10, 0.50, None), ("up", -0.10, 0.50, None), ("down", 0.10, 0.50, None), ("down", -0.10, 0.50, None),
        ("down", -0.06, 0.20, deadline), ("down", -0.03, 0.20, deadline),
    ]
    out = []
    for direction, change, probability, end_date in rows:
        title = "Oil hits $115 by November 30?" if end_date else "Will it happen?"
        item = SimpleNamespace(
            id="x", title=title, url=None, source="polymarket", change_24h=change, probability=probability,
            end_date=end_date, volume_24h=MARKET_MIN_VOLUME,
        )
        tag = SimpleNamespace(direction=direction, reason="")
        ev = _market_evidence(tag, item, now)  # type: ignore[arg-type]
        out.append(MarketCase(
            yes_is_good=direction == "up", change=change, deadline=end_date is not None,
            contribution=ev.contribution if ev else 0.0,
        ))
    return out


# What's new

_STOP = set(
    "para como sobre desde entre hasta pero porque cuando donde este esta estos estas todo todos "
    "with from that this have will their about after into over says said than more".split()
)


def _words(text: str) -> set[str]:
    plain = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    return {w for w in re.findall(r"[a-z0-9]+", plain) if len(w) > 3 and w not in _STOP}


def similarity(a: set[str], b: set[str]) -> float:
    return len(a & b) / math.sqrt(len(a) * len(b)) if a and b else 0.0


def drop_repeats(items: list[tuple[datetime, str, Evidence | None]]) -> list[Evidence]:
    """Items about one ticker, as (published, text, evidence or None if it no longer counts). Each
    is compared only with earlier ones: what repeats one of them isn't new, whatever its outlet. A
    repeat adds a source to the one it repeats, when that one still counts."""
    seen: list[tuple[datetime, set[str]]] = []
    kept: list[Evidence] = []
    position: dict[int, int] = {}  # index in seen -> index in kept
    for when, text, ev in sorted(items, key=lambda x: x[0]):
        words = _words(text)
        original = next(
            (k for k, (at, w) in enumerate(seen)
             if when - at <= timedelta(days=NOVELTY_DAYS) and similarity(words, w) >= NOVELTY_SIMILARITY),
            None,
        )
        if original is not None:
            if original in position:
                at = position[original]
                kept[at] = kept[at].model_copy(update={"sources": kept[at].sources + 1})
            continue
        if ev is not None:
            position[len(seen)] = len(kept)
            kept.append(ev)
        seen.append((when, words))
    return kept


def collect_signals(now: datetime | None = None) -> dict[str, list[Evidence]]:
    """Evidence per ticker: its own news and markets, plus the markets reaching it through a factor."""
    now = now or datetime.now(timezone.utc)
    impacts = _recent_impacts(now)
    news = _fetch_by_ids("news_items", NewsRow, list({i.item_id for i in impacts if i.item_kind == "news"}))
    markets = _fetch_by_ids(
        "prediction_markets", MarketRow, list({i.item_id for i in impacts if i.item_kind == "market"}),
    )

    per_ticker: dict[str, list[tuple[datetime, str, Evidence | None]]] = {}
    # Per (ticker, event), the market that counts: one naming the ticker over a factor's, then the
    # most traded. Not the one that moved the most: that would pick the noise.
    by_event: dict[tuple[str, str], tuple[tuple[bool, float], Evidence]] = {}
    seen: set[tuple[str, str]] = set()
    for imp in impacts:
        if (imp.item_id, imp.ticker) in seen:
            continue
        seen.add((imp.item_id, imp.ticker))
        if imp.item_kind == "news":
            n = news.get(imp.item_id)
            if n:
                per_ticker.setdefault(imp.ticker, []).append((
                    n.published_at or n.created_at, f"{n.title} {n.summary or ''}", _news_evidence(imp, n, now),
                ))
            continue
        m = markets.get(imp.item_id)
        ev = _market_evidence(imp, m, now) if m else None
        if not m or not ev:
            continue
        direct = not factors.is_factor(imp.ticker)
        reached = {imp.ticker: 1} if direct else factors.reach(imp.ticker)
        for ticker, sign in reached.items():
            this = ev if direct else ev.model_copy(update={
                "value": ev.value * sign, "weight": ev.weight * FACTOR_WEIGHT,
                "contribution": round(ev.contribution * sign * FACTOR_WEIGHT, 4),
                "direction": ev.direction if sign > 0 else ("down" if ev.direction == "up" else "up"),
                "via": factors.FACTORS[imp.ticker].label,
            })
            key = (ticker, m.event_key or m.id)
            rank = (direct, m.volume_24h or 0)
            if key not in by_event or rank > by_event[key][0]:
                by_event[key] = (rank, this)

    signals = {t: drop_repeats(items) for t, items in per_ticker.items()}
    for (ticker, _), (_, ev) in by_event.items():
        signals.setdefault(ticker, []).append(ev)
    return {t: evs for t, evs in signals.items() if evs}


def score_of(evidence: list[Evidence]) -> float:
    return sum(e.weight * e.value for e in evidence) / (sum(e.weight for e in evidence) + PRIOR_WEIGHT)


def rank_by_class(recs: list["Recommendation"]) -> None:
    """Fill each ticker's place within its asset class, among those with evidence."""
    classes: dict[str, list[Recommendation]] = {}
    for r in recs:
        if r.evidence and r.score != 0:
            classes.setdefault(r.breakdown.asset_class or "otros", []).append(r)
    for rs in classes.values():
        rs.sort(key=lambda r: -r.score)
        # A factor gives the same score to all it reaches: equal scores share their place, so the
        # alphabet doesn't choose among them.
        cutoff = rs[max(1, math.ceil(len(rs) * TOP_SHARE)) - 1].score
        for r in rs:
            r.breakdown.rank = next(k for k, x in enumerate(rs, 1) if x.score == r.score)
            r.breakdown.rank_of, r.breakdown.top_rank = len(rs), r.score >= cutoff


def decide(score: float, held: bool, top_rank: bool, out_of_profile: bool) -> Action:
    if held:
        return "sell" if score <= SELL_THRESHOLD_HELD else "keep"
    return "buy" if top_rank and score >= BUY_THRESHOLD and not out_of_profile else "keep"


def is_buy_signal(r: RecommendationRow) -> bool:
    """Whether this recommendation asks to buy, for a portfolio that doesn't hold it. What it says
    depended on the real portfolio, and the simulation has its own."""
    b = r.signal_breakdown
    if r.model_version < 2:
        return not b.out_of_profile and r.score - b.concentration >= V1_BUY
    return decide(r.score, False, b.top_rank, b.out_of_profile) == "buy"


def is_sell_signal(r: RecommendationRow) -> bool:
    if r.model_version < 2:
        return r.score - r.signal_breakdown.concentration <= V1_SELL
    return r.score <= SELL_THRESHOLD_HELD


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


def three_month_context(bars: list[DailyBar], price: float) -> tuple[float | None, float | None]:
    """(change over ~3 months, distance from the 3-month high), shown next to a signal."""
    window = [b for b in bars if b.close > 0][-63:]
    if len(window) < 40 or price <= 0:
        return None, None
    high = max(max(b.high for b in window), price)
    return price / window[0].close - 1, price / high - 1


class Recommendation(BaseModel):
    ticker: str
    action: Action
    score: float
    held: bool
    price: float | None
    breakdown: SignalBreakdown
    evidence: list[Evidence]


@dataclass
class _Inputs:
    ticker: str
    held: bool
    price: float | None
    evidence: list[Evidence] = field(default_factory=list)
    asset_class: str | None = None
    change_3m: float | None = None
    from_high: float | None = None
    macro: float = 0.0
    macro_source: str | None = None
    macro_level: float | None = None
    macro_change: float | None = None
    event: corporate_events.CorporateEvent | None = None
    risk: suitability.RiskLevel | None = None
    profile: suitability.Profile = "conservador"


def _combine(i: _Inputs) -> Recommendation:
    """The score alone. The action needs the ranking: see recommend()."""
    out_of_profile = i.risk is not None and not suitability.allowed(i.risk.level, i.profile)
    evidence = sorted(i.evidence, key=lambda e: abs(e.contribution), reverse=True)
    news = sum(e.contribution for e in evidence if e.kind == "news")
    markets = sum(e.contribution for e in evidence if e.kind == "market")
    return Recommendation(
        ticker=i.ticker, action="keep", score=round(score_of(evidence), 4), held=i.held, price=i.price,
        breakdown=SignalBreakdown(
            news=round(news, 4), markets=round(markets, 4), asset_class=i.asset_class,  # type: ignore[arg-type]
            change_3m=round(i.change_3m, 4) if i.change_3m is not None else None,
            from_high=round(i.from_high, 4) if i.from_high is not None else None,
            macro=round(i.macro, 4), macro_source=i.macro_source,  # type: ignore[arg-type]
            macro_level=i.macro_level,
            macro_change=round(i.macro_change, 4) if i.macro_change is not None else None,
            event_kind=i.event.kind if i.event else None,  # type: ignore[arg-type]
            event_date=i.event.ex_date if i.event else None,
            event_yield=round(i.event.yield_, 5) if i.event and i.event.yield_ is not None else None,
            risk_level=i.risk.level if i.risk else None,
            volatility=round(i.risk.volatility, 4) if i.risk and i.risk.volatility is not None else None,
            profile=i.profile, out_of_profile=out_of_profile,
        ),
        evidence=evidence,  # all of it: the page adds it up to the score
    )


def recommend(inputs: list[_Inputs]) -> list[Recommendation]:
    recs = [_combine(i) for i in inputs]
    rank_by_class(recs)
    for r in recs:
        r.action = decide(r.score, r.held, r.breakdown.top_rank, r.breakdown.out_of_profile)
    return recs


def pick_scored(tickers: set[str], held: set[str], signals: dict[str, list[Evidence]]) -> set[str]:
    """At most MAX_SCORED tickers, so a cycle fits its time: holdings always, then the ones with
    the strongest news and markets of their own."""
    if len(tickers) <= MAX_SCORED:
        return tickers
    strength = lambda t: sum(abs(e.contribution) for e in signals.get(t, []))
    rest = sorted(tickers - held, key=lambda t: (-strength(t), t))
    log.warning("scoring %d of %d tickers", MAX_SCORED, len(tickers))
    return held | set(rest[: max(0, MAX_SCORED - len(held))])


def compute(now: datetime | None = None) -> list[Recommendation]:
    """Score every ticker with evidence plus every holding. Saves nothing."""
    signals = collect_signals(now)
    holdings: dict[str, Holding]
    try:
        holdings = {h.ticker: h for h in get_holdings()}
    except Exception:
        log.exception("could not load holdings; scoring without portfolio")
        holdings = {}

    g = universe.groups()
    stocks = g.stocks | {t for t, h in holdings.items() if h.type in EQUITY_TYPES}
    bonds = g.bonds | {t for t, h in holdings.items() if h.type in BOND_TYPES}
    cedears = g.cedears | {t for t, h in holdings.items() if h.type in CEDEAR_TYPES}
    known = stocks | bonds | cedears
    tickers = pick_scored({t for t in signals if t in known} | set(holdings), set(holdings), signals)

    profile = suitability.INVESTOR_PROFILE
    try:
        kinds = asset_types(tickers)
    except Exception:
        log.exception("no asset types; every asset counts as high risk")
        kinds = {}
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
        live = universe.live_prices()
    except Exception:
        log.warning("no panel prices; asking IOL ticker by ticker")
        live = {}

    inputs: list[_Inputs] = []
    for ticker in sorted(tickers):
        group = "stocks" if ticker in stocks else "bonds" if ticker in bonds else "us" if ticker in cedears else None
        bars: list[DailyBar] = []
        try:
            bars = prices.daily_bars(ticker, days=100)
        except Exception:
            # IOL answers some bonds' history with a 500 (seen with TXMD9).
            log.warning("no history for %s", ticker)
        price: float | None = live.get(ticker)
        if not price:
            try:
                price = get_iol().quote(ticker).price or None
            except Exception:
                log.warning("no live price for %s; using the last close", ticker)
        if not price and bars:
            price = bars[-1].close
        macro_value, macro_source = macro_for(ticker, group, macro_signals)
        ms = macro_signals.get(macro_source) if macro_source else None
        change_3m, from_high = three_month_context(bars, price) if price else (None, None)
        inputs.append(_Inputs(
            ticker=ticker, held=ticker in holdings, price=price, evidence=signals.get(ticker, []),
            asset_class=group, change_3m=change_3m, from_high=from_high,
            macro=macro_value, macro_source=macro_source,
            macro_level=ms.level if ms else None, macro_change=ms.change if ms else None,
            event=events.get(ticker),
            risk=suitability.risk_level(ticker, kinds.get(ticker), bars), profile=profile,
        ))
    return recommend(inputs)


def score_all(kinds: tuple[str, ...] = ("live",), now: datetime | None = None) -> list[Recommendation]:
    """Score and save. kinds: "live" is what the site shows; "daily" is the batch that gets graded,
    saved together with "live" just before the open, so what is measured is what was shown."""
    recs = compute(now)
    if recs:
        target = market_hours.next_close_date(now)
        rows = [{
            "ticker": r.ticker,
            "action": r.action,
            "score": r.score,
            "held": r.held,
            "price_at_rec": r.price,
            "signal_breakdown": r.breakdown.model_dump(mode="json"),  # dates (event_date) as text
            "evidence": [e.model_dump(mode="json") for e in r.evidence],
            "target_date": target.isoformat(),
            "kind": kind,
            "model_version": MODEL_VERSION,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        } for r in recs for kind in kinds]
        get_db().table("recommendations").upsert(rows, on_conflict="ticker,target_date,kind").execute()
        log.info("scored %d tickers (%s) for %s", len(recs), ",".join(kinds), target)
    return recs
