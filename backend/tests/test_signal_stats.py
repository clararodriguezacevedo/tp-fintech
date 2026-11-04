from datetime import date, datetime, timedelta, timezone

import pytest

from app.analysis import evaluation, scoring, simulation, track_record
from app.models.db import RecommendationRow, SignalBreakdown
from app.models.iol import DailyBar

NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)
D1, D2 = date(2026, 10, 1), date(2026, 10, 2)


def row(ticker, day, ret, action="keep", news=0.0, score=0.0, cls="us", excess=None, version=2, close=None):
    return RecommendationRow(
        id=f"{ticker}{day}", ticker=ticker, action=action, kind="daily", score=score, model_version=version, held=False,
        signal_breakdown=SignalBreakdown(news=news, markets=0, asset_class=cls), evidence=[], target_date=day,  # type: ignore[arg-type]
        realized_return=ret, excess_return=excess, close_return=close, created_at=NOW, updated_at=NOW,
    )


# Grading

@pytest.mark.parametrize("action, excess, hit", [("buy", 0.01, True), ("buy", -0.01, False), ("sell", -0.01, True), ("sell", 0.01, False), ("keep", 0.01, None)])
def test_a_call_is_right_if_it_beat_its_class_and_keeping_is_no_call(action, excess, hit):
    assert track_record.is_hit(action, excess) == hit


def test_excess_is_against_the_median_of_its_own_class():
    rows = [row("A", D1, -0.01), row("B", D1, -0.03), row("C", D1, -0.05), row("X", D1, 0.05, cls="bonds"), row("Y", D1, 0.01, cls="bonds"), row("Z", D1, 0.03, cls="bonds")]
    excess = track_record.excess_returns(rows)
    assert excess[f"A{D1}"] == pytest.approx(0.02)  # it fell, but beat its class
    assert excess[f"X{D1}"] == pytest.approx(0.02)


def test_a_class_too_small_has_no_excess():
    assert track_record.excess_returns([row("A", D1, 0.01), row("B", D1, 0.02)]) == {}


def test_signals_are_measured_against_the_class_and_macro_is_marked_as_not_scored():
    rows = [row("A", D1, -0.01, news=0.5, excess=0.02), row("B", D1, -0.03, news=-0.5, excess=-0.02), row("C", D1, 0.0, news=0.5, excess=-0.01), row("D", D2, 0.0, news=0.0, excess=0.01)]
    stats = {s.signal: s for s in track_record.signal_stats(rows)}
    assert (stats["news"].n, stats["news"].hits, stats["news"].days) == (3, 2, 1)
    assert stats["news"].in_score and not stats["macro"].in_score
    assert stats["macro"].rate is None


# Evaluation

def ranked_day(day, spread_sign=1, n=10):
    """n tickers whose open -> close follows the score, or goes against it."""
    return [row(f"T{k}", day, spread_sign * k / 100, score=k / 10) for k in range(n)]


def bars_for(rows):
    """Bars where each ticker opens at 100 and closes as its row says, one per target day."""
    per: dict[str, list[DailyBar]] = {}
    for r in sorted(rows, key=lambda r: r.target_date):
        c = 100 * (1 + (r.realized_return or 0))
        per.setdefault(r.ticker, []).append(DailyBar(day=r.target_date, open=100, high=max(100, c), low=min(100, c), close=c))
    return lambda t: per.get(t, [])


def test_a_signal_that_works_beats_its_placebos():
    rows = [r for k in range(6) for r in ranked_day(D1 + timedelta(days=k))]
    t = evaluation.check_signal(rows, bars_for(rows), 2, runs=50)
    h1 = t.horizons[0]
    assert h1.days == 1 and h1.spread_bp == pytest.approx(800)
    assert h1.top_net_bp["20"] == pytest.approx(h1.top_bp - 20)
    assert t.inverted_bp == pytest.approx(-800)
    assert t.placebo_tickers is not None and t.placebo_tickers.share_at_least_real < 0.1
    assert t.sessions == 6 and not t.enough


def test_too_few_per_day_isnt_a_ranking():
    rows = [row("A", D1, 0.01, score=0.5), row("B", D1, -0.01, score=-0.5), row("C", D1, 0.0)]
    t = evaluation.check_signal(rows, bars_for(rows), 2, runs=5)
    assert t.horizons == [] and t.placebo_tickers is None


def test_an_open_outside_the_candle_isnt_used():
    r = row("A", D1, 0.0)
    assert evaluation.forward_returns([r], lambda _: [DailyBar(day=D1, open=120, high=110, low=95, close=105)], 1) == {}


def test_overnight_is_what_close_to_close_has_beyond_open_to_close():
    r = row("A", D1, 0.01, close=0.0302)
    assert evaluation.overnight_returns([r])[r.id] == pytest.approx(0.02)


# The rules the simulation replays

def test_each_model_is_replayed_with_its_own_rules():
    old = row("A", D1, 0.0, score=0.35, version=1)
    new = row("A", D1, 0.0, score=0.35, version=2)
    assert scoring.is_buy_signal(old)
    assert not scoring.is_buy_signal(new)  # not in the top of its class
    top = new.model_copy(update={"signal_breakdown": new.signal_breakdown.model_copy(update={"top_rank": True})})
    assert scoring.is_buy_signal(top)
    assert scoring.is_sell_signal(row("A", D1, 0.0, score=-0.5, version=1))
    assert not scoring.is_sell_signal(row("A", D1, 0.0, score=-0.5, version=2))


def test_series_stats():
    s = simulation.series_stats([110.0, 99.0, 121.0], 100.0)
    assert s is not None
    assert s.total_return == pytest.approx(0.21)
    assert s.max_drawdown == pytest.approx(-0.1)
    assert s.sortino is not None and s.sortino > 0
    assert simulation.series_stats([], 100.0) is None
