from datetime import date, datetime, timedelta

import pytest

from app.analysis import scoring
from app.analysis.scoring import TickerSignals, _combine, _Inputs
from app.models.db import Evidence
from app.models.iol import DailyBar
from app.sources.macro import MacroSignal


def ev(item_id: str, contribution: float, kind: str = "news", since: datetime | None = None) -> Evidence:
    return Evidence(
        kind=kind, item_id=item_id, title=f"noticia {item_id}", direction="up" if contribution >= 0 else "down",  # type: ignore[arg-type]
        strength="high", reason="", contribution=contribution, since=since,
    )


def bars(n: int, close: float = 100.0, spread: float = 2.0, end: date = date(2026, 10, 22)) -> list[DailyBar]:
    """n weekday candles ending on `end`, flat at `close` with a high-low range of `spread`."""
    out, day = [], end
    while len(out) < n:
        if day.weekday() < 5:
            out.append(DailyBar(day=day, open=close, high=close + spread / 2, low=close - spread / 2, close=close))
        day -= timedelta(days=1)
    return out[::-1]


def inputs(**kw) -> _Inputs:
    base = dict(ticker="X", held=False, price=100.0, own=[], broad=[], trend=0.0, context=0.0)
    return _Inputs(**(base | kw))  # type: ignore[arg-type]


# Market wrap-ups

@pytest.mark.parametrize("title", [
    "Jornada financiera: las acciones argentinas rebotaron hasta 6%",
    "Así cerró el mercado: bonos en alza y riesgo país en baja",
    "Merval cerró en verde impulsado por los bancos",
    "Stocks rose on Friday as tech rallied",
    "Acciones argentinas cayeron hasta 5% en Wall Street",
    "El Merval subió 2% de la mano de los bancos",
])
def test_recaps_are_detected(title):
    assert scoring.is_market_recap(title)


@pytest.mark.parametrize("title", [
    "El BCRA bajó la tasa de política monetaria",
    "Galicia presentó balances con ganancias récord",
    "YPF anunció una inversión de US$ 5.000 millones en Vaca Muerta",
    "Acciones bajo presión por la suba de tasas en EE.UU.",
])
def test_news_is_not_a_recap(title):
    assert not scoring.is_market_recap(title)


# Counting once, sectors, concentration and thresholds

def test_news_tagged_for_ticker_and_merval_counts_for_both():
    rec = _combine(inputs(own=[ev("a", 1.0)], broad=[ev("a", 1.0), ev("b", 1.0)]), gap=0.0)
    assert sorted((e.item_id, e.broad) for e in rec.evidence) == [("a", False), ("a", True), ("b", True)]
    assert rec.breakdown.news == pytest.approx(1.0 + 2 * scoring.BROAD_WEIGHT)


def test_sector_news_spreads_at_reduced_weight():
    signals = {"GGAL": TickerSignals(evidence=[ev("a", 0.5)]), "BMA": TickerSignals(evidence=[ev("b", 1.0)])}
    peers = scoring.sector_evidence("BMA", signals)
    assert [(e.item_id, e.via) for e in peers] == [("a", "GGAL")]
    rec = _combine(inputs(ticker="BMA", own=signals["BMA"].evidence, sector=peers), gap=0.0)
    assert rec.breakdown.news == pytest.approx(1.0 + 0.5 * scoring.SECTOR_WEIGHT)


def test_sector_news_already_tagged_on_the_ticker_counts_once():
    signals = {"GGAL": TickerSignals(evidence=[ev("a", 1.0)])}
    rec = _combine(inputs(ticker="BMA", own=[ev("a", 1.0)], sector=scoring.sector_evidence("BMA", signals)), gap=0.0)
    assert len(rec.evidence) == 1 and rec.evidence[0].via is None


def test_many_small_sector_items_are_capped():
    signals = {"NVDA": TickerSignals(evidence=[ev(f"n{k}", 0.6) for k in range(6)])}
    rec = _combine(inputs(ticker="MSFT", sector=scoring.sector_evidence("MSFT", signals)), gap=0.0)
    assert rec.breakdown.news == pytest.approx(scoring.SECTOR_CAP, abs=1e-3)
    one = _combine(inputs(ticker="MSFT", sector=[ev("x", 0.5).model_copy(update={"via": "NVDA"})]), gap=0.0)
    assert one.breakdown.news == pytest.approx(0.5 * scoring.SECTOR_WEIGHT)


@pytest.mark.parametrize("title", [
    "Big Tech's earnings are on deck. There's more for investors to watch than AI spending",
    "Qué mirar esta semana en el mercado",
])
def test_a_tagged_preview_counts(title):
    from datetime import timezone

    from app.models.db import NewsRow, TickerImpactRow

    now = datetime(2026, 11, 3, 12, tzinfo=timezone.utc)
    imp = TickerImpactRow(id="i", item_kind="news", item_id="n", ticker="MSFT", direction="up", strength="medium", created_at=now)
    item = NewsRow.model_construct(id="n", title=title, url=None, published_at=now, created_at=now)
    e = scoring._news_evidence(imp, item, now)
    assert e is not None and e.contribution == pytest.approx(scoring.STRENGTH["medium"])


def test_the_prompt_asks_for_the_expectation_of_a_preview():
    from app.analysis import tagger

    assert "sentiment and the expectation" in tagger.prompt_for_display()


def test_unrelated_sectors_dont_spread():
    assert scoring.sector_evidence("KO", {"GGAL": TickerSignals(evidence=[ev("a", 1.0)])}) == []


@pytest.mark.parametrize("share, penalty", [(None, 0.0), (0.5, 0.0), (0.6, 0.0), (0.7, -0.2), (0.95, -0.3)])
def test_concentration_penalty(share, penalty):
    assert scoring.concentration_penalty(share) == pytest.approx(penalty)


def test_concentration_only_affects_buys():
    strong = [ev("a", 3.0)]
    free = _combine(inputs(own=strong, group_share=0.2), gap=0.0)
    heavy = _combine(inputs(own=strong, group_share=0.7), gap=0.0)
    held = _combine(inputs(own=strong, group_share=0.7, held=True), gap=0.0)
    assert heavy.score == pytest.approx(free.score - 0.2)
    assert held.breakdown.concentration == 0


def test_selling_needs_a_stronger_signal_than_buying():
    def score_of(c: float, held: bool):
        return _combine(inputs(own=[ev("a", c)], held=held), gap=0.0)

    mild = -0.9  # 0.65 * tanh(-0.45) = -0.27... below the buy bar's mirror, above the sell bar
    medium = -1.6  # about -0.43
    assert score_of(mild, held=True).action == "keep"
    assert score_of(medium, held=True).score > scoring.SELL_THRESHOLD_HELD
    assert score_of(medium, held=True).action == "keep"
    assert score_of(-3.0, held=True).action == "sell"
    assert score_of(1.6, held=False).action == "buy"


# Macro

def test_macro_signal_routes_by_group():
    signals = {"riesgo_pais": MacroSignal(level=700, change=0.1, signal=0.6),
               "ccl": MacroSignal(level=1600, change=0.02, signal=0.5)}
    assert scoring.macro_for("AL30", "bonds", signals) == (-0.6, "riesgo_pais")
    assert scoring.macro_for("GGAL", "stocks", signals) == (-0.6, "riesgo_pais")
    assert scoring.macro_for("TXAR", "stocks", signals) == (-0.3, "riesgo_pais")
    assert scoring.macro_for("VIST", "us", signals) == (-0.3, "riesgo_pais")
    assert scoring.macro_for("KO", "us", signals) == (0.5, "ccl")
    assert scoring.macro_for("KO", "us", {}) == (0.0, None)


# Three-month context

def test_three_month_context():
    b = bars(70)
    b[-63] = b[-63].model_copy(update={"close": 80.0})
    b[-10] = b[-10].model_copy(update={"high": 125.0})
    change, from_high = scoring.three_month_context(b, 100.0)
    assert change == pytest.approx(0.25)
    assert from_high == pytest.approx(100 / 125 - 1)
    assert scoring.three_month_context(bars(20), 100.0) == (None, None)


def test_broken_accents_are_detected():
    from app.analysis.tagger import TaggedItem, TickerImpact, has_broken_accents

    ok = TaggedItem(id="a", summary="La suba del petróleo favorece a YPF.", impacts=[])
    bad = TaggedItem(id="b", summary="Bien.", impacts=[
        TickerImpact(ticker="YPFD", direction="up", strength="low", reason="La suba del petr3leo favorece a YPF."),
    ])
    assert not has_broken_accents(ok)
    assert has_broken_accents(bad)
    assert not has_broken_accents(TaggedItem(id="c", summary="Subió 3% en el G20 y el S3.", impacts=[]))


def test_markets_about_to_resolve_dont_count_and_many_markets_are_capped():
    from datetime import timezone

    from app.models.db import MarketRow, TickerImpactRow

    now = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)
    imp = TickerImpactRow(id="i", item_kind="market", item_id="m", ticker="VIST", direction="up", strength="high", created_at=now)

    def market(days):
        return MarketRow.model_construct(
            id="m", source="polymarket", title="WTI", url=None, probability=0.1, change_24h=-0.2,
            end_date=now + timedelta(days=days),
        )

    assert scoring._market_evidence(imp, market(-5), now) is None  # already over
    assert scoring._market_evidence(imp, market(1), now) is None  # moves by the clock
    assert scoring._market_evidence(imp, market(30), now) is not None

    many = [ev(str(k), -0.5, kind="market") for k in range(4)] + [ev("n", 0.4)]
    rec = _combine(inputs(own=many), gap=0.0)
    assert rec.breakdown.markets == pytest.approx(-scoring.MARKETS_CAP)
    assert rec.breakdown.news == pytest.approx(0.4)  # news isn't scaled


@pytest.mark.parametrize("title, deadline", [
    ("Will WTI Crude Oil (WTI) hit (HIGH) $115 in November?", True),
    ("Will Trump meet with Javier Milei by November 30, 2026?", True),
    ("Will Gold (GC) hit (HIGH) $5,000 by end of December?", True),
    ("Next Fed rate cut?: Before July 2027", True),
    ("Will Amazon be the third-largest company in the world by market cap?", False),
    ("Fed funds rate at end of 2027: Above 2.25%", False),
    ("Will Mauricio Macri win the 2027 Argentina presidential election?", False),
])
def test_deadline_markets_are_detected(title, deadline):
    assert scoring.is_deadline_market(title) == deadline


def test_time_decay_grows_near_the_deadline():
    far = scoring.time_decay(0.40, 0.0, 60)
    near = scoring.time_decay(0.40, 0.0, 5)
    assert near < far < 0
    assert far == pytest.approx(-0.0049, abs=0.001)
    assert near == pytest.approx(-0.0540, abs=0.002)
    assert scoring.time_decay(0.0, 0.0, 5) == 0
    assert scoring.time_decay(0.4, 0.0, 0) == 0


def test_only_the_move_beyond_the_clock_counts():
    from datetime import timezone

    from app.models.db import MarketRow, TickerImpactRow

    now = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)
    imp = TickerImpactRow(id="i", item_kind="market", item_id="m", ticker="VIST", direction="up", strength="high", created_at=now)

    def market(title, prob, change, days=5):
        return MarketRow.model_construct(
            id="m", source="polymarket", title=title, url=None, probability=prob, change_24h=change,
            end_date=now + timedelta(days=days),
        )

    # Falls about what the clock explains: no signal.
    assert scoring._market_evidence(imp, market("Will WTI hit $115 in November?", 0.36, -0.04), now) is None
    # Falls more: only the rest counts, and the detail says how much was the clock.
    e = scoring._market_evidence(imp, market("Will WTI hit $115 in November?", 0.30, -0.10), now)
    assert e is not None and -1 < e.contribution < 0
    assert abs(e.contribution) < 1.0 * 0.10 / scoring.MARKET_MOVE_UNIT
    assert "paso del tiempo" in e.detail
    # Not a deadline market: the whole move counts.
    same = scoring._market_evidence(imp, market("Fed funds rate at end of 2027: Above 2.25%", 0.30, -0.10), now)
    assert same is not None and same.contribution == pytest.approx(-1.0)
    assert "paso del tiempo" not in same.detail
