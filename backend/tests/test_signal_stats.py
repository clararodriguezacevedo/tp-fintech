from types import SimpleNamespace

from app.analysis import track_record
from app.models.db import SignalBreakdown


def test_news_and_markets_are_measured_as_the_score_uses_them():
    b = SignalBreakdown(news=0.5, markets=-0.2, trend=0.1, context=0.0, gap=0.0)
    assert abs(track_record._signal_value(b, "evidence") - 0.3) < 1e-9
    assert track_record._signal_value(b, "trend") == 0.1
    # News for and markets against that cancel out point nowhere.
    even = SignalBreakdown(news=0.5, markets=-0.5, trend=0.0, context=0.0, gap=0.0)
    assert abs(track_record._signal_value(even, "evidence")) < track_record.SIGNAL_MIN


def test_each_signal_has_a_weight_in_the_score():
    from app.analysis import scoring

    weights = SimpleNamespace(evidence=scoring.W_EVIDENCE, trend=scoring.W_TREND, context=scoring.W_CONTEXT, gap=scoring.W_GAP, macro=scoring.W_MACRO)
    assert all(hasattr(weights, name) for name in track_record.SIGNALS)
    assert abs(sum(getattr(weights, name) for name in track_record.SIGNALS) - 1.0) < 1e-9
