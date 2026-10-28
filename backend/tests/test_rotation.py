import pytest

from app.analysis import rotation
from app.analysis.rotation import Candidate, Held

TOTAL = 1_000_000


def held(ticker: str, score: float, value: float = 100_000, quantity: float = 100, action: str = "keep", out: bool = False):
    return Held(ticker=ticker, score=score, value=value, quantity=quantity, action=action, out_of_profile=out)


def summary(plan):
    return [(s.action, s.ticker, s.quantity, s.why, s.pair) for s in plan.steps]


def test_buys_use_cash_first():
    plan = rotation.build(cash=200_000, total=TOTAL, held=[held("KO", -0.5)], buys=[Candidate("MSFT", 0.5, 1_000, 100_000)])
    assert summary(plan) == [("buy", "MSFT", 100, "cash", None)]
    assert plan.cash_left == pytest.approx(100_000)


def test_no_cash_rotates_out_of_a_much_weaker_position():
    plan = rotation.build(cash=0, total=TOTAL, held=[held("KO", -0.2)], buys=[Candidate("MSFT", 0.4, 1_000, 50_000)])
    assert summary(plan) == [("sell", "KO", 50, "rotation", "MSFT"), ("buy", "MSFT", 50, "rotation", "KO")]
    assert plan.unfunded == []


def test_no_rotation_when_the_gap_is_small_or_the_holding_is_strong():
    small_gap = rotation.build(cash=0, total=TOTAL, held=[held("KO", 0.05)], buys=[Candidate("MSFT", 0.35, 1_000, 50_000)])
    strong = rotation.build(cash=0, total=TOTAL, held=[held("KO", 0.2)], buys=[Candidate("MSFT", 0.9, 1_000, 50_000)])
    for plan in (small_gap, strong):
        assert plan.steps == []
        assert [u.ticker for u in plan.unfunded] == ["MSFT"]


def test_recommended_sells_fund_buys_and_out_of_profile_goes_first():
    plan = rotation.build(
        cash=0, total=TOTAL,
        held=[held("VIST", -0.6, action="sell"), held("NVDA", 0.0, out=True), held("KO", -0.3)],
        buys=[Candidate("MSFT", 0.5, 1_000, 150_000)],
    )
    assert summary(plan)[:2] == [("sell", "VIST", 100, "recommended", None), ("buy", "MSFT", 100, "cash", None)]
    # The other 50.000: from the position outside the profile, even though KO scores lower.
    assert summary(plan)[2:] == [("sell", "NVDA", 50, "rotation", "MSFT"), ("buy", "MSFT", 50, "rotation", "NVDA")]


def test_tiny_trades_are_left_out():
    plan = rotation.build(cash=500_000, total=TOTAL, held=[], buys=[Candidate("MSFT", 0.5, 1_000, 5_000)])
    assert plan.steps == [] and plan.unfunded == []


def test_money_adds_up():
    plan = rotation.build(
        cash=30_000, total=TOTAL, held=[held("KO", -0.4, value=80_000, quantity=40)],
        buys=[Candidate("MSFT", 0.5, 1_000, 100_000)],
    )
    spent = sum(s.amount for s in plan.steps if s.action == "buy")
    raised = sum(s.amount for s in plan.steps if s.action == "sell")
    assert plan.cash + raised - spent == pytest.approx(plan.cash_left)
