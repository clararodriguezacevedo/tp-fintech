from datetime import date, datetime, timezone
from unittest.mock import MagicMock

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
        id="r", ticker="KO", action=action, kind="daily", score=0, held=held,  # type: ignore[arg-type]
        signal_breakdown=SignalBreakdown(news=0, markets=0), evidence=[], price_at_rec=price,
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
    assert g["realized_return"] == pytest.approx(99 / 98 - 1, abs=1e-6)  # the dividend doesn't touch open -> close


def test_coupon_of_unknown_size_drops_the_overnight_gap():
    event = CorporateEvent(ticker="KO", ex_date=BAR.day, kind="coupon", source="t")
    g = track_record._grade(rec(), BAR, event)
    assert g["close_return"] == g["realized_return"]


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


# Investor profile

def _flat_bars(daily_move: float, n: int = 61) -> list[DailyBar]:
    out, price = [], 100.0
    for k in range(n):
        price *= 1 + (daily_move if k % 2 else -daily_move)
        out.append(DailyBar(day=date(2026, 1, 1), open=price, high=price, low=price, close=price))
    return out


def test_risk_levels_by_kind_and_volatility():
    from app.analysis import suitability as s

    calm, mid, wild = _flat_bars(0.003), _flat_bars(0.012), _flat_bars(0.03)  # ~5%, ~19%, ~48% a year
    assert s.risk_level("AL30", "TIT. PUBLICOS", calm).level == 1
    assert s.risk_level("AL30", "TitulosPublicos", mid).level == 2
    assert s.risk_level("KO", "CEDEARS", mid).level == 2
    assert s.risk_level("SPY", "CEDEARS", mid).kind == "etf"
    assert s.risk_level("GGAL", "ACCIONES", wild).level == 3
    assert s.risk_level("XYZ", None, calm).level == 3  # unknown kind is never safe
    assert s.risk_level("KO", "CEDEARS", []).level == 3  # no history is never safe


def test_profiles_allow_up_to_their_level():
    from app.analysis import suitability as s

    assert s.allowed(1, "conservador") and not s.allowed(2, "conservador")
    assert s.allowed(2, "moderado") and not s.allowed(3, "moderado")
    assert s.allowed(3, "arriesgado")


# Account value

def test_unsettled_buys_are_not_counted_twice(monkeypatch):
    """Real balances of 2026-11-01: four buys of 30/10 unsettled, already in the positions."""
    from datetime import datetime, timezone

    from app import account, portfolio
    from app.models.iol import Balances

    balances = Balances.model_validate({
        "ars": {"currency": "ARS", "totals": {"t0": 1129278.69}, "available": {"t0": 11047.57}, "committed": {"t0": 1118231.12}},
        "usd": {"currency": "USD", "totals": {"t0": 12.84}, "available": {"t0": 12.84}, "committed": {"t0": 0}},
    })
    monkeypatch.setattr(portfolio, "get_iol", lambda: type("I", (), {"balances": lambda self: balances})())
    assert portfolio._fetch_cash() == (11047.57, 12.84)

    monkeypatch.setattr(account, "mep_rate", lambda: 1588.67924528)
    holding = portfolio.Holding(
        ticker="X", description="", type="CEDEARS", quantity=1, last_price=6004449.42, avg_price=1, value=6004449.42, gain_pct=0,
    )
    snap = portfolio.Snapshot(captured_at=datetime.now(timezone.utc), holdings=[holding], cash_ars=11047.57, cash_usd=12.84)
    assert account.value_of(snap).total == pytest.approx(6035895.63, abs=0.05)  # IOL's close of 31/10


def test_a_pending_order_stays_in_the_total_but_cant_be_spent(monkeypatch):
    """Real balances of 2026-11-02: an order for 280.000 pending, 169,40 of fees on top."""
    from datetime import datetime, timezone
    from types import SimpleNamespace

    from app import account, portfolio
    from app.models.iol import Balances, Executed, Trade

    balances = Balances.model_validate({
        "ars": {
            "currency": "ARS", "totals": {"t0": 11047.57, "t1": 449567.85},
            "available": {"t0": 11047.57, "t1": 169398.45}, "committed": {"t0": 0, "t1": 280169.4},
        },
        "usd": {"currency": "USD", "totals": {"t0": 0}, "available": {"t0": 0}, "committed": {"t0": 0}},
    })
    when = datetime(2026, 11, 2, 19, 40)
    pending = Trade(
        order_id=1, order_date=when, type="Compra", status="pending", symbol="ALUA", currency="ARS",
        order=Executed(qty=0, price=814, amount=280000),
    )
    done = Trade(
        order_id=2, order_date=when, type="Compra", status="completed", symbol="GGAL", currency="ARS",
        order=Executed(qty=1, price=1, amount=999),
    )
    fake = SimpleNamespace(balances=lambda: balances, operations=lambda start, end: [pending, done])
    monkeypatch.setattr(portfolio, "get_iol", lambda: fake)

    cash, _ = portfolio._fetch_cash()
    assert cash == pytest.approx(11047.57 + 169398.45 + 280000)
    snap = portfolio.Snapshot(captured_at=datetime.now(timezone.utc), holdings=[], cash_ars=cash, cash_usd=0)
    value = account.value_of(snap)
    assert value.total == pytest.approx(cash)
    assert value.reserved_ars == 280000


def test_the_check_against_iol_waits_for_todays_close(monkeypatch):
    from datetime import datetime

    from app import reconcile
    from app.analysis import market_hours

    morning = datetime(2026, 11, 3, 7, 10, tzinfo=market_hours.ART)
    monkeypatch.setattr(market_hours, "now_art", lambda: morning)
    # Before the close it asks IOL for nothing: this would fail if it did.
    monkeypatch.setattr(reconcile, "get_iol", lambda: 1 / 0)
    monkeypatch.setattr(reconcile, "latest", lambda: 1 / 0)
    assert reconcile.run() is None


# Trades on the price chart

def _op(symbol, kind="Compra", status="completed", currency="ARS", qty=10.0, price=100.0):
    from app.models.iol import Executed, Trade

    when = datetime(2026, 10, 5, 12, 45)
    return Trade(order_id=1, order_date=when, execution_date=when, type=kind, status=status, symbol=symbol,
                 currency=currency, executed=Executed(qty=qty, price=price, amount=qty * price))


def test_trades_include_the_dollar_species_and_only_real_buys_and_sells():
    from app.trading.history import from_operations

    ops = [
        _op("VIST"), _op("VISTD", currency="USD", price=23.03), _op("VIST", kind="Venta"),
        _op("VIST", status="cancelled"), _op("VIST", kind="Pago de Dividendos", qty=0), _op("VIST", qty=0),
        _op("VISTA"), _op("GGAL"), _op("VISTD"),  # a peso "VISTD" isn't the dollar species
    ]
    got = from_operations(ops, "VIST")
    assert [(t.side, t.currency, t.price) for t in got] == [("buy", "ARS", 100.0), ("buy", "USD", 23.03), ("sell", "ARS", 100.0)]
    assert got[0].day == date(2026, 10, 5)
    # YPFD is a peso ticker of its own, not YPF's dollar species.
    assert from_operations([_op("YPFD")], "YPF") == []


def test_trades_before_a_split_are_restated_like_the_chart():
    from app import prices
    from app.schemas import TickerTrade
    from app.trading.history import adjust_for_splits

    days = [date(2026, 7, 31), date(2026, 8, 3)]
    raw = [DailyBar(day=days[0], open=83000, high=83000, low=83000, close=83000),
           DailyBar(day=days[1], open=8100, high=8100, low=8100, close=8105)]
    before = TickerTrade(day=date(2026, 7, 30), side="buy", quantity=5, price=82750, currency="ARS")
    after = TickerTrade(day=date(2026, 8, 3), side="sell", quantity=50, price=8100, currency="ARS")
    got = adjust_for_splits([before, after], raw, prices.adjust_splits(raw))
    assert (got[0].quantity, got[0].price, got[0].split_adjusted) == (50, 8275, True)
    assert got[1] == after


# The universe

def _row(symbol, last=100.0, currency="ARS", name="X"):
    return {"instrument": {"symbol": symbol, "name": name, "currency": currency}, "quotes": {"last": last}}


def test_universe_keeps_priced_peso_assets_and_flags_groups():
    from app import universe

    panels = {
        "acciones": [_row("GGAL", name="Grupo Galicia"), _row("GGALD", currency="USD"), _row("DEAD", last=0)],
        "cedears": [_row("KO", name="Cedear The Coca Cola Company"), _row("KOD", currency="USD"), _row("GGAL")],
        "bonos": [_row("AL30"), _row("BLL26", last=0)],
    }
    got = {a.ticker: a for a in universe.build_assets(panels, {"GGAL"}, {"AL30"})}
    assert sorted(got) == ["AL30", "GGAL", "KO"]
    assert got["GGAL"].category == "acciones" and got["GGAL"].leader and not got["KO"].leader
    assert got["AL30"].sovereign and got["KO"].name == "The Coca Cola Company"


def test_scoring_keeps_holdings_and_the_strongest_news_when_over_the_cap(monkeypatch):
    from app.analysis import scoring
    from app.models.db import Evidence

    monkeypatch.setattr(scoring, "MAX_SCORED", 3)
    ev = lambda c: Evidence(kind="news", item_id="a", title="t", direction="up", reason="", contribution=c)
    signals = {"A": [ev(0.1)], "B": [ev(0.9)], "C": [ev(-0.5)]}
    assert scoring.pick_scored({"A", "B", "C", "HELD"}, {"HELD"}, signals) == {"HELD", "B", "C"}
    assert scoring.pick_scored({"A", "HELD"}, {"HELD"}, signals) == {"A", "HELD"}


# Checks against IOL and the day's median

def test_account_check_tolerates_price_timing_but_not_counting_errors():
    from app import reconcile

    day = date(2026, 10, 30)
    assert reconcile.compare(day, 5049765, 5054767).ok  # the worst real day: -0.10%
    assert not reconcile.compare(day, 7154127, 6035896).ok  # unsettled buys counted twice
    assert not reconcile.compare(day, 6307660, 6035896).ok
    assert reconcile.compare(day, 5000000, 5100000, transfers_after=100000).ok  # a deposit after the snapshot


def test_last_trading_day_skips_weekends():
    from app import reconcile

    assert reconcile.last_trading_day(date(2026, 11, 2)) == date(2026, 10, 30)  # Monday -> Friday
    assert reconcile.last_trading_day(date(2026, 11, 3)) == date(2026, 11, 2)
