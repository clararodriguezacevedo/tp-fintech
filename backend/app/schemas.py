"""Request and response models of our own API that aren't table rows (those are in
app.models.db). FastAPI publishes all of them in /openapi.json, which the frontend uses to
generate its zod schemas."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.db import Direction, MarketRow, NewsRow


class Health(BaseModel):
    ok: bool
    market_open: bool
    next_open: datetime
    live_trading: bool
    mode: Literal["paper", "live"]


class Impact(BaseModel):
    ticker: str
    direction: Direction


class NewsOut(NewsRow):
    impacts: list[Impact]


class MarketOut(MarketRow):
    impacts: list[Impact]


class JobResult(BaseModel):
    failed: list[str]
    skipped: bool = False


class ProbabilityPoint(BaseModel):
    t: datetime
    p: float = Field(ge=0, le=1)


class AccountSummary(BaseModel):
    total_value: float  # whole account in pesos, as IOL values it
    cash_ars: float
    cash_usd: float


class PortfolioValuePoint(BaseModel):
    t: datetime
    value: float  # pesos: IOL's closing value of the whole account that day
    value_usd_mep: float | None = None  # same value in dollars at that day's MEP rate


class Transfer(BaseModel):
    day: date
    amount: float  # pesos; positive = deposit, negative = withdrawal


class TradePlan(BaseModel):
    entry: float
    stop_loss: float
    take_profit: float
    quantity: int
    max_loss: float
    market_open: bool
    fees: float | None = None  # commission + VAT + market fee IOL estimates for this order
    # The quantity each limit allows; quantity is the smallest, and limited_by names it.
    limits: dict[Literal["risk", "cash", "position", "concentration", "liquidity"], int] = {}
    limited_by: Literal["risk", "cash", "position", "concentration", "liquidity"] | None = None
    portfolio_share: float | None = None  # the buy as a share of the portfolio
    risk_level: int | None = None  # 1 bajo, 2 medio, 3 alto
    volatility: float | None = None  # annualized
    profile: Literal["conservador", "moderado", "arriesgado"] | None = None
    out_of_profile: bool = False  # buying needs accept_out_of_profile


class BuyRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=12)
    quantity: int = Field(gt=0)
    stop_loss: float = Field(gt=0)
    take_profit: float = Field(gt=0)
    recommendation_id: str | None = None
    accept_out_of_profile: bool = False  # the user confirmed buying above their profile


class PlanStep(BaseModel):
    action: Literal["sell", "buy"]
    ticker: str
    quantity: int
    amount: float  # pesos
    score: float
    why: Literal["recommended", "rotation", "cash"]  # sell: recommended or to pay a buy; buy: cash or rotation
    group: int  # a rotation's sell and buy share it
    pair: str | None = None  # the other ticker of a rotation


class UnfundedBuy(BaseModel):
    ticker: str
    score: float
    amount: float  # pesos the plan couldn't pay for


class CaucionSuggestion(BaseModel):
    """Lending what the plan leaves idle (app.caucion)."""

    amount: float  # the plan's cash_left
    term_days: int
    due_date: date
    rate: float  # nominal annual, as a fraction
    rate_at: datetime
    live: bool  # False: the last rate seen, the market is closed
    gain: float  # interest over the term, before costs
    costs: float | None  # None if IOL couldn't estimate them


class PortfolioPlan(BaseModel):
    """Today's plan for the whole portfolio, within the money there is (app.analysis.rotation)."""

    cash: float  # pesos available before the plan
    cash_left: float  # after it
    steps: list[PlanStep]
    unfunded: list[UnfundedBuy]
    rotation_gap: float
    min_trade: float  # share of the portfolio below which a trade is left out
    caucion: CaucionSuggestion | None = None


class TickerTrade(BaseModel):
    """A buy or sell of a ticker, for its price chart."""

    day: date
    side: Literal["buy", "sell"]
    quantity: float
    price: float  # per unit as traded, in `currency` (bonds: per 100 nominal)
    currency: Literal["ARS", "USD"]
    simulated: bool = False
    split_adjusted: bool = False  # price and quantity restated for a later split, like the chart


class Operation(BaseModel):
    """A real buy or sell in IOL, done or still waiting to execute."""

    id: str
    at: datetime
    side: Literal["buy", "sell"]
    ticker: str  # the asset: VIST also for VISTD, its dollar species
    status: Literal["completed", "pending"]
    quantity: float  # 0 for a pending order placed by amount
    price: float  # per unit, in `currency` (bonds: per 100 nominal)
    currency: Literal["ARS", "USD"]
    amount: float  # in `currency`
    result: float | None = None  # sells, in pesos: what it brought minus its average cost
    cost: float | None = None  # sells with a result, in pesos: that average cost
    rate: float | None = None  # that day's MEP rate, to show it in the other currency


class OperationsOut(BaseModel):
    operations: list[Operation]  # newest first
    realized: float  # sum of the results


class AssetOut(BaseModel):
    ticker: str
    name: str
    category: Literal["acciones", "cedears", "bonos"]


class SellRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=12)
    quantity: int = Field(gt=0)
    recommendation_id: str | None = None


class SellPlan(BaseModel):
    """What selling a position would bring, before confirming."""

    ticker: str
    held: int  # units in the portfolio
    price: float  # last price, per unit as IOL quotes it (bonds: per 100 nominal)
    value_per_unit: float  # pesos one unit is worth at that price
    cost_per_unit: float  # pesos one unit cost
    fees: float | None = None  # IOL's estimate for selling all of it
    market_open: bool


class HoldingOut(BaseModel):
    ticker: str
    description: str
    type: str
    currency: Literal["ARS", "USD"]
    quantity: float
    last_price: float
    avg_price: float
    value: float
    gain_pct: float
    gain_amount: float
    day_change_pct: float


class PortfolioOut(BaseModel):
    """The account now. total_ars = the holdings in pesos + cash_ars + cash_usd_ars, the same
    definition as every point of /portfolio/history (app.account)."""

    captured_at: datetime  # when these prices were read from IOL
    holdings: list[HoldingOut]
    cash_ars: float  # pesos in the account, what pending buy orders hold back included
    reserved_ars: float = 0.0  # that part: it counts in the total, but can't be spent
    cash_usd: float
    mep: float | None  # pesos per dollar used for cash_usd_ars
    cash_usd_ars: float  # cash_usd in pesos at the MEP rate
    total_ars: float


class Quote(BaseModel):
    price: float
    change_pct: float  # versus the previous close, as a fraction
    previous_close: float | None
    live: bool  # False when IOL didn't answer and this is the last stored close


class SignalStats(BaseModel):
    signal: Literal["news", "markets", "macro"]
    in_score: bool  # macro is measured, but doesn't decide
    n: int  # graded recommendations where this signal pointed somewhere
    hits: int  # ... and the asset did better or worse than its class's median as it said
    rate: float | None
    days: int  # different trading days behind these numbers


class MarketCase(BaseModel):
    """What the scoring gives a market's move, for a high-strength tag."""

    yes_is_good: bool  # whether its YES coming true is good for the ticker
    change: float  # probability move in 24 hours
    deadline: bool  # a "by a date" market with 5 days left and a 20% chance
    contribution: float


class FactorInfo(BaseModel):
    key: str
    label: str
    up: list[str]  # rise with the factor
    down: list[str]  # fall with the factor


class ModelInfo(BaseModel):
    """The model's constants, so the "Cómo decide" page always matches the code."""

    version: int
    prior_weight: float
    top_share: float  # of each class, that can be bought
    buy_threshold: float
    sell_threshold_held: float
    news_max_opens: int
    novelty_days: int
    novelty_similarity: float
    market_move_unit: float
    market_min_move: float
    market_min_volume: float
    min_market_days: int
    far_market_days: int
    far_market_min_weight: float
    factor_weight: float
    factors: list[FactorInfo]
    market_cases: list[MarketCase]
    concentration_limit: float
    risk_per_trade: float  # for the user's profile
    max_position: float  # for the user's profile
    profile: Literal["conservador", "moderado", "arriesgado"]
    bond_low_vol: float
    equity_mid_vol: float
    max_volume_share: float
    tagger_model: str
    news_prompt: str
    market_prompt: str
    tag_batch: int
