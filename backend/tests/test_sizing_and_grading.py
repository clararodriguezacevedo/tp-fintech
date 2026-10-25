from datetime import date, datetime, timezone

import pytest

from app.analysis import risk, track_record
from app.models.db import RecommendationRow, SignalBreakdown
from app.models.iol import DailyBar
from app.sources import corporate_events, macro
from app.sources.corporate_events import CorporateEvent


# Buy sizing

def plan(**kw):
    base = dict(entry=100.0, atr_value=2.0, portfolio_value=1_000_000, risk_per_trade=0.01, cash_available=1e9)
    return risk.plan_buy(**(base | kw))  # type: ignore[arg-type]


def test_risk_limits_volatile_tickers_more():
    calm, wild = plan(atr_value=1.0, risk_per_trade=0.001), plan(atr_value=4.0, risk_per_trade=0.001)
    assert calm.limited_by == wild.limited_by == "risk"
    assert calm.quantity == 4 * wild.quantity == 500  # 1.000 at risk / (2 x 1 peso)


def test_cash_caps_the_buy():
    p = plan(cash_available=50_000)
    assert (p.limited_by, p.quantity) == ("cash", 500)


def test_position_cap_counts_what_is_held():
    p = plan(atr_value=0.5, held_value=60_000)  # risk would allow 10.000 shares
    assert (p.limited_by, p.quantity) == ("position", 400)  # 100.000 cap - 60.000 held


def test_concentration_room_and_floor():
    room = plan(atr_value=0.5, group_value=570_000)
    assert (room.limited_by, room.quantity) == ("concentration", 300)  # 600.000 - 570.000
    over = plan(atr_value=0.5, group_value=700_000)
    assert (over.limited_by, over.quantity) == ("concentration", 200)  # at most 2% more


def test_liquidity_cap():
    p = plan(avg_volume=1_000)
    assert (p.limited_by, p.quantity) == ("liquidity", 100)
    assert p.portfolio_share == pytest.approx(0.01)


# Grading with dividends and coupons

def rec(price: float = 100.0, action: str = "keep", held: bool = True) -> RecommendationRow:
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    return RecommendationRow(
        id="r", ticker="KO", action=action, kind="daily", score=0, confidence=0, held=held,  # type: ignore[arg-type]
        signal_breakdown=SignalBreakdown(news=0, markets=0, trend=0), evidence=[], price_at_rec=price,
        target_date=date(2026, 10, 2), created_at=now, updated_at=now,
    )


BAR = DailyBar(day=date(2026, 10, 2), open=98.0, high=99.5, low=97.5, close=99.0)


def test_grade_without_events():
    g = track_record._grade(rec(), BAR)
    assert g["close_return"] == pytest.approx(-0.01)
    assert g["realized_return"] == pytest.approx(99 / 98 - 1, abs=1e-6)


def test_dividend_is_added_back_to_close_return():
    event = CorporateEvent(ticker="KO", ex_date=BAR.day, kind="dividend", amount=2, yield_=0.02, source="t")
    g = track_record._grade(rec(), BAR, event)
    assert g["close_return"] == pytest.approx(0.01)
    assert g["event_yield"] == 0.02
    assert g["hit"] is True  # graded open -> close, which the dividend doesn't touch


def test_coupon_of_unknown_size_drops_the_overnight_gap():
    event = CorporateEvent(ticker="KO", ex_date=BAR.day, kind="coupon", source="t")
    g = track_record._grade(rec(), BAR, event)
    assert g["close_return"] == g["realized_return"]


@pytest.mark.parametrize("score, bucket", [(0.1, (0.0, 0.15)), (-0.32, (0.3, 0.45)), (0.99, (0.6, 1.01))])
def test_score_bucket(score, bucket):
    assert track_record.score_bucket(score) == bucket


# Corporate events and macro

def test_coupon_dates_skip_weekends():
    # 9 Jan 2027 is a Saturday: paid Monday the 11th, so the ex-date is Friday the 8th.
    assert corporate_events.coupon_ex_dates(2027) == [date(2027, 1, 8), date(2027, 7, 8)]


def test_us_symbols_map_to_local_tickers():
    tradable = {"YPFD", "GGAL", "BRKB"}
    assert corporate_events._local_ticker("YPF", tradable) == "YPFD"
    assert corporate_events._local_ticker("GGAL", tradable) == "GGAL"
    assert corporate_events._local_ticker("BRK/B", tradable) == "BRKB"
    assert corporate_events._local_ticker("KO", tradable) is None


def test_macro_signal_sign_and_size():
    calm = [100 + (i % 2) for i in range(60)]
    jump = calm[:-1] + [120.0]
    s = macro.change_signal(jump)
    assert s is not None and s.signal > 0.9 and s.level == 120
    fall = macro.change_signal(calm[:-1] + [80.0])
    assert fall is not None and fall.signal < -0.9
    assert macro.change_signal([100.0] * 10) is None


# Splits

def test_split_is_adjusted_but_normal_gaps_are_not():
    from app import prices

    days = [date(2026, 7, 30), date(2026, 7, 31), date(2026, 8, 3), date(2026, 8, 4)]
    raw = [DailyBar(day=d, open=o, high=c, low=c, close=c, volume=v)
           for d, o, c, v in zip(days, [80_000, 82_000, 8_100, 8_300], [82_000, 83_000, 8_105, 8_200], [10, 10, 100, 100])]
    adj = prices.adjust_splits(raw)
    assert [b.close for b in adj] == [8_200, 8_300, 8_105, 8_200]
    assert adj[0].volume == 100
    gap = raw[:2] + [raw[2].model_copy(update={"open": 70_000.0, "close": 70_000.0})]
    assert prices.adjust_splits(gap) == gap
