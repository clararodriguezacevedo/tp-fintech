"""The day's plan for the whole portfolio: what to sell, what to buy, and with which money.

Buy recommendations alone would keep asking to buy more, as if cash were endless. This turns
them into a plan that fits the money there is:

  1. Positions recommended to sell are sold; the money joins the cash.
  2. Buys go from the best score down, each sized like the buy panel sizes it, and are paid
     with cash first.
  3. When cash runs out, a buy can be paid by rotating out of a held position: only one the
     buy beats by ROTATION_GAP or more in score, and that isn't itself expected to rise
     (score <= ROTATION_MAX_HELD_SCORE). Positions outside the investor profile go first, then
     the lowest scores. Only what the buy needs is sold.
  4. A buy nothing can pay for is reported as such instead of recommended anyway.

Trades smaller than MIN_TRADE of the portfolio are left out: they cost more than they move.
"""

import math
from dataclasses import dataclass, field
from typing import Literal

ROTATION_GAP = 0.35
ROTATION_MAX_HELD_SCORE = 0.10
MIN_TRADE = 0.01


@dataclass
class Held:
    ticker: str
    score: float
    value: float  # pesos
    quantity: float
    action: str  # today's recommendation: "sell" or "keep"
    out_of_profile: bool = False
    left: float = field(init=False)

    def __post_init__(self):
        self.left = self.value

    @property
    def unit_value(self) -> float:
        return self.value / self.quantity if self.quantity else 0.0


@dataclass
class Candidate:
    ticker: str
    score: float
    price: float  # per unit, as the buy panel uses it
    target: float  # pesos the buy panel would put in


@dataclass
class Step:
    action: Literal["sell", "buy"]
    ticker: str
    quantity: int
    amount: float
    score: float
    why: Literal["recommended", "rotation", "cash"]
    group: int  # a sell and the buy it pays for share a group
    pair: str | None = None  # the other side of a rotation


@dataclass
class Unfunded:
    ticker: str
    score: float
    amount: float  # pesos that couldn't be paid for


@dataclass
class Plan:
    cash: float
    cash_left: float
    steps: list[Step]
    unfunded: list[Unfunded]


def _sell_quantity(h: Held, amount: float) -> int:
    """Whole units worth at least `amount`, at most the whole position."""
    if h.unit_value <= 0:
        return 0
    return min(int(h.quantity), math.ceil(amount / h.unit_value - 1e-9))


def build(cash: float, total: float, held: list[Held], buys: list[Candidate], cost_rate: float = 0.0) -> Plan:
    steps: list[Step] = []
    unfunded: list[Unfunded] = []
    minimum = MIN_TRADE * total
    pool = max(cash, 0.0)
    group = 0

    for h in sorted(held, key=lambda h: h.score):
        if h.action == "sell" and h.value > 0:
            group += 1
            steps.append(Step("sell", h.ticker, int(h.quantity), round(h.value, 2), h.score, "recommended", group))
            pool += h.value * (1 - cost_rate)
            h.left = 0.0

    for b in sorted(buys, key=lambda b: -b.score):
        need = b.target
        if need < minimum or b.price <= 0:
            continue
        group += 1
        from_cash = min(pool, need)
        if from_cash >= minimum:
            qty = int(from_cash / b.price)
            if qty > 0:
                steps.append(Step("buy", b.ticker, qty, round(qty * b.price, 2), b.score, "cash", group))
                pool -= qty * b.price
                need -= qty * b.price
        while need >= minimum:
            donors = [
                h for h in held
                if h.left >= minimum and b.score - h.score >= ROTATION_GAP and h.score <= ROTATION_MAX_HELD_SCORE
            ]
            if not donors:
                break
            d = min(donors, key=lambda h: (not h.out_of_profile, h.score))
            sell_qty = _sell_quantity(d, min(need, d.left))
            raised = sell_qty * d.unit_value
            buy_qty = int(raised * (1 - cost_rate) / b.price)
            if sell_qty <= 0 or buy_qty <= 0:
                break
            group += 1
            steps.append(Step("sell", d.ticker, sell_qty, round(raised, 2), d.score, "rotation", group, pair=b.ticker))
            steps.append(Step("buy", b.ticker, buy_qty, round(buy_qty * b.price, 2), b.score, "rotation", group, pair=d.ticker))
            d.left -= raised
            pool += raised * (1 - cost_rate) - buy_qty * b.price  # leftover from rounding stays as cash
            need -= buy_qty * b.price
        if need >= minimum:
            unfunded.append(Unfunded(b.ticker, b.score, round(need, 2)))

    return Plan(cash=round(cash, 2), cash_left=round(pool, 2), steps=steps, unfunded=unfunded)
