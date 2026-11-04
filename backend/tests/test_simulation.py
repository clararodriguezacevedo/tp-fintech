from datetime import date

import pytest

from app.analysis import risk
from app.analysis.simulation import Book, Position, exit_price, follow_day, opening_price
from app.models.db import RecommendationRow, SignalBreakdown
from app.models.iol import DailyBar

DAY = date(2026, 11, 2)


def bar(open_=100.0, high=100.0, low=100.0, close=100.0):
    return DailyBar(day=DAY, open=open_, high=high, low=low, close=close, volume=1000)


def rec(ticker, score):
    return RecommendationRow.model_construct(
        ticker=ticker, score=score, model_version=2,
        signal_breakdown=SignalBreakdown.model_construct(concentration=0.0, out_of_profile=False, top_rank=True),
    )


def size(ticker, entry, total, group_value):
    return risk.TradePlan(entry=entry, stop_loss=entry * 0.9, take_profit=entry * 1.2, quantity=int(0.1 * total / entry), max_loss=0)


def run(book, bars, recs=None, cost=0.0):
    return follow_day(book, bars, recs or {}, {}, cost, lambda t: "exterior", size)


def test_a_position_carries_over_and_earns_every_day():
    book = Book(cash=0.0, positions={"KO": Position(1000.0, 100.0)})
    run(book, {"KO": bar(110, 111, 109, 110)})
    run(book, {"KO": bar(110, 121, 110, 121)})
    assert book.positions["KO"].value == pytest.approx(1210)


def test_a_buy_stays_with_its_stop_and_target_until_the_stop_hits():
    book = Book(cash=10_000.0)
    trades = run(book, {"MSFT": bar()}, {"MSFT": rec("MSFT", 0.5)})
    assert list(trades.bought) == ["MSFT"] and book.positions["MSFT"].stop == 90
    trades = run(book, {"MSFT": bar(95, 96, 89, 92)})
    assert trades.stopped == ["MSFT"] and "MSFT" not in book.positions
    assert book.total == pytest.approx(9000 + 1000 * 0.9)


def test_the_stop_counts_when_both_are_inside_one_candle():
    p = Position(100.0, 100.0, stop=90.0, take=120.0)
    assert exit_price(p, bar(100, 125, 85, 100), at_open=False) == (90.0, "stop")


def test_a_gap_through_the_stop_fills_at_the_open():
    book = Book(cash=0.0, positions={"KO": Position(1000.0, 100.0, stop=90.0, take=120.0)})
    trades = run(book, {"KO": bar(80, 85, 78, 84)})
    assert trades.stopped == ["KO"] and book.cash == pytest.approx(800)


def test_an_open_outside_the_candle_counts_as_its_edge():
    # IOL repeated the previous close as the open: 120 would fill the target, which never traded.
    p = Position(100.0, 100.0, stop=70.0, take=120.0)
    assert opening_price(bar(120, 110, 95, 105)) == 110
    assert exit_price(p, bar(120, 110, 95, 105), at_open=True) is None


def test_take_profit_fills_at_its_price():
    book = Book(cash=0.0, positions={"KO": Position(1000.0, 100.0, stop=90.0, take=120.0)})
    trades = run(book, {"KO": bar(100, 125, 99, 124)})
    assert trades.took_profit == ["KO"] and book.cash == pytest.approx(1200)


def test_a_sold_position_is_not_sold_again():
    book = Book(cash=0.0, positions={"QQQ": Position(1000.0, 100.0)})
    first = run(book, {"QQQ": bar()}, {"QQQ": rec("QQQ", -0.7)})
    second = run(book, {"QQQ": bar()}, {"QQQ": rec("QQQ", -0.7)})
    assert first.sold == ["QQQ"] and second.sold == [] and book.cash == pytest.approx(1000)


def test_costs_are_charged_on_the_buy():
    book = Book(cash=10_000.0)
    run(book, {"MSFT": bar()}, {"MSFT": rec("MSFT", 0.5)}, cost=0.01)
    assert book.total == pytest.approx(10_000 - 1000 * 0.01)
