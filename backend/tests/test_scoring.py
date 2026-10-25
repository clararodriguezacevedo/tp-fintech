from datetime import date, datetime, timedelta

import pytest

from app.analysis import market_hours, scoring
from app.analysis.scoring import TickerSignals, _close_before, _combine, _Inputs
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


# Reference price for "already in the price"

def at(day: date, hour: int) -> datetime:
    return datetime(day.year, day.month, day.day, hour, tzinfo=market_hours.ART)


def test_news_during_the_session_compares_with_the_previous_close():
    b = bars(5, end=date(2026, 10, 23))  # Friday's candle is there (written after the close)
    b[-1] = b[-1].model_copy(update={"close": 110.0})
    assert _close_before(b, at(date(2026, 10, 23), 15)) == 100.0
    assert _close_before(b, at(date(2026, 10, 23), 21)) == 100.0


def test_weekend_news_compares_with_fridays_close():
    b = bars(5, end=date(2026, 10, 23))
    b[-1] = b[-1].model_copy(update={"close": 110.0})
    assert _close_before(b, at(date(2026, 10, 24), 12)) == 110.0


def test_fully_priced_in_news_stops_counting():
    b = bars(30)  # ATR = 2 on a price of 100, so a typical day is 2%
    since = at(date(2026, 10, 22), 21)  # after Thursday's close: the reference is Wednesday's
    moved = scoring.discount_priced_in([ev("a", 1.0, since=since)], b, price=100 * (1 + 1.5 * 0.02))
    assert moved[0].contribution == 0
    assert moved[0].priced_in == 1


def test_news_against_the_move_keeps_its_weight():
    b = bars(30)
    moved = scoring.discount_priced_in([ev("a", -1.0, since=at(date(2026, 10, 22), 21))], b, price=103.0)
    assert moved[0].contribution == -1.0


# Counting once, sectors, concentration and thresholds

def test_news_tagged_for_ticker_and_merval_counts_once():
    rec = _combine(inputs(own=[ev("a", 1.0)], broad=[ev("a", 1.0), ev("b", 1.0)]), gap=0.0)
    assert sorted((e.item_id, e.broad) for e in rec.evidence) == [("a", False), ("b", True)]
    assert rec.breakdown.news == pytest.approx(1.0 + scoring.BROAD_WEIGHT)


def test_sector_news_spreads_at_reduced_weight():
    signals = {"GGAL": TickerSignals(evidence=[ev("a", 1.0)]), "BMA": TickerSignals(evidence=[ev("b", 1.0)])}
    peers = scoring.sector_evidence("BMA", signals)
    assert [(e.item_id, e.via) for e in peers] == [("a", "GGAL")]
    rec = _combine(inputs(ticker="BMA", own=signals["BMA"].evidence, sector=peers), gap=0.0)
    assert rec.breakdown.news == pytest.approx(1.0 + scoring.SECTOR_WEIGHT)


def test_sector_news_already_tagged_on_the_ticker_counts_once():
    signals = {"GGAL": TickerSignals(evidence=[ev("a", 1.0)])}
    rec = _combine(inputs(ticker="BMA", own=[ev("a", 1.0)], sector=scoring.sector_evidence("BMA", signals)), gap=0.0)
    assert len(rec.evidence) == 1 and rec.evidence[0].via is None


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
