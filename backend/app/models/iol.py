"""IOL Inversiones API responses (https://developers.iolinversiones.com), typed from real
responses captured on 2026-10-23.

Every response is wrapped as {"meta": ..., "data": ..., "error": ...}; the client unwraps
`data`. Only the fields we use are declared; unknown fields are ignored so a new field doesn't
break parsing, but a missing or retyped field we rely on fails loudly.
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class IOLModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class ApiError(IOLModel):
    message: str
    code: str | int | None = None


class Token(IOLModel):
    """POST /auth/token"""

    access_token: str
    refresh_token: str
    expires_in: int
    expires_at: datetime
    token_type: str


# Accounts

class BySettlement(IOLModel):
    """Amounts by settlement term, each term on its own (a sale settling tomorrow is in t1)."""

    t0: float
    t1: float = 0
    t2: float = 0
    t3: float = 0

    @property
    def total(self) -> float:
        return self.t0 + self.t1 + self.t2 + self.t3


class CurrencyBalance(IOLModel):
    currency: str
    totals: BySettlement
    available: BySettlement
    committed: BySettlement


class Balances(IOLModel):
    """GET /broker/accounts/AR/balances"""

    ars: CurrencyBalance
    usd: CurrencyBalance


class Instrument(IOLModel):
    symbol: str
    name: str
    type: str  # "ACCIONES", "CEDEARS", "TIT. PUBLICOS", ...
    asset_class: str
    exchange: str
    currency: str  # "ARS" or "USD"


class MarketValue(IOLModel):
    current_price: float
    price_change: float
    price_change_percent: float


class ProfitLoss(IOLModel):
    unrealized_pl: float
    unrealized_pl_percent: float


class CostBasis(IOLModel):
    average_entry_price: float
    total_cost: float


class Position(IOLModel):
    instrument: Instrument
    quantity: float
    market_value: MarketValue
    profit_loss: ProfitLoss
    cost_basis: CostBasis
    portfolio_weight_percent: float

    @property
    def price_unit(self) -> int:
        """Bonds are quoted per 100 nominal (the API's total_cost doesn't divide by it)."""
        return 100 if "PUBLICOS" in self.instrument.type.upper() or "OBLIGACIONES" in self.instrument.type.upper() else 1

    @property
    def value(self) -> float:
        return self.quantity * self.market_value.current_price / self.price_unit

    @property
    def gain_amount(self) -> float:
        """From value and percent, which are right for bonds too."""
        return self.value - self.value / (1 + self.profit_loss.unrealized_pl_percent / 100)


class Positions(IOLModel):
    """GET /broker/accounts/AR/positions?valuation_currency=ARS"""

    account: str
    currency: str
    total_market_value: float
    positions: list[Position]


class Equity(IOLModel):
    ars: float
    usd_mep: float
    usd_ccl: float


class ExchangeRate(IOLModel):
    mep: float
    ccl: float


class HistoryDay(IOLModel):
    date: date
    equity: Equity
    exchange_rate: ExchangeRate


class AccountHistory(IOLModel):
    """GET /broker/accounts/AR/portfolio/history (end date must be before today)"""

    status: Literal["complete", "partial"]
    history: list[HistoryDay]


class Movement(IOLModel):
    """One item of GET /broker/accounts/activities: buys, sells, deposits, withdrawals..."""

    activity_type: str  # "Buy", "Sell", "Deposit", "Withdrawal", "Dividend Payment", ...
    trade_date: datetime
    currency: str  # "ARS" or "US$"
    net_amount: float  # what came into (+) or left (-) the account's cash


class Trade(IOLModel):
    """One item of GET /broker/accounts/activities/operations"""

    order_id: str | int
    order_date: datetime
    type: str
    status: str
    symbol: str
    currency: str


# Market data

class Prices(IOLModel):
    current: float
    open: float
    close: float
    high: float
    low: float
    previous_close: float


class Change(IOLModel):
    amount: float
    percent: float


class Quote(IOLModel):
    """GET /broker/market-data/{symbol}/quote?market=BCBA|NYSE|NASDAQ&term=T1"""

    symbol: str
    market: str
    currency: str
    prices: Prices
    change: Change
    last_updated: datetime

    @property
    def price(self) -> float:
        return self.prices.current


class Bar(IOLModel):
    """One row of GET /broker/market-data/{symbol}/bars. Some symbols come one row per day,
    others several per day, each carrying the day's open/high/low so far."""

    datetime: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class Bars(IOLModel):
    symbol: str
    market: str
    bars: list[Bar]


class DailyBar(BaseModel):
    """Our own daily candle, built from Bar rows."""

    day: date
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None  # shares traded that day


class BookSide(IOLModel):
    price: float
    size: float


class Book(IOLModel):
    bid: BookSide
    ask: BookSide


class ScreenerQuotes(IOLModel):
    last: float
    open: float
    close: float
    high: float
    low: float
    change_percent: float
    volume: float


class ScreenerInstrument(IOLModel):
    symbol: str
    name: str
    market: str
    currency: str


class ScreenerRow(IOLModel):
    """One item of GET /broker/market-data/screener?panel=argaccionesmerval"""

    instrument: ScreenerInstrument
    quotes: ScreenerQuotes
    book: Book


class OptionInfo(IOLModel):
    type: Literal["call", "put"]
    strike_price: float
    state: str


class OptionRow(IOLModel):
    """One item of GET /broker/market-data/{symbol}/options"""

    symbol: str
    option: OptionInfo
    quotes: ScreenerQuotes
    book: Book


class RepoTerm(IOLModel):
    """One item of GET /broker/market-data/repos/terms (cauciones)"""

    term_id: int
    term_days: int
    min_amount: float
    max_amount: float
    due_date: datetime


# Orders

class Money(IOLModel):
    currency: str
    value: float


class RegulatoryFees(IOLModel):
    vat: Money
    market_fee: Money


class OrderEstimate(IOLModel):
    """POST /broker/orders/estimate: previews costs, places nothing."""

    amount: Money
    commission: Money
    regulatory_fees: RegulatoryFees

    @property
    def total_cost(self) -> float:
        return self.commission.value + self.regulatory_fees.vat.value + self.regulatory_fees.market_fee.value

    @property
    def cost_rate(self) -> float:
        return self.total_cost / self.amount.value if self.amount.value else 0.0


class OrderResult(BaseModel):
    """POST /broker/orders. Not captured yet (no real order has been sent), so every field is
    optional and the raw body is kept."""

    model_config = ConfigDict(extra="allow")
    order_id: str | int | None = None
    status: str | None = None
