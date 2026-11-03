"""Every buy and sell of one ticker, for marking them on its price chart.

Real ones come from IOL's operations and simulated ones from trade_intents. A ticker's dollar
species is the same asset bought with dollars (VISTD and VISTC for VIST, AO27D for AO27), so
those count too, in the currency they were traded in.
"""

import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Literal

from app import prices
from app.analysis import market_hours
from app.brokers.iol import get_iol
from app.db import get_db, rows_as
from app.models.db import TradeRow
from app.models.iol import DailyBar, Trade
from app.schemas import Operation, OperationsOut, TickerTrade

log = logging.getLogger(__name__)

SIDES: dict[str, Literal["buy", "sell"]] = {"Compra": "buy", "Venta": "sell"}
HISTORY_DAYS = 365
FIRST_DAY = date(2015, 1, 1)


def from_operations(ops: list[Trade], ticker: str) -> list[TickerTrade]:
    """Completed buys and sells of `ticker`; cancelled orders, dividends and the rest are left out."""
    dollar_species = {f"{ticker}{s}" for s in ("D", "C", ".D", ".C")}  # BMA's is BMA.D
    out = []
    for o in ops:
        side = SIDES.get(o.type)
        same_asset = o.symbol == ticker or (o.currency == "USD" and o.symbol in dollar_species)
        if not side or not same_asset or o.status != "completed" or o.executed is None or o.executed.qty <= 0:
            continue
        out.append(TickerTrade(
            day=(o.execution_date or o.order_date).date(), side=side, quantity=o.executed.qty,  # type: ignore[arg-type]
            price=o.executed.price, currency="USD" if o.currency == "USD" else "ARS",
        ))
    return out


def from_simulated(rows: list[TradeRow]) -> list[TickerTrade]:
    out = []
    for t in rows:
        if t.fill_price is None or t.filled_at is None or t.status == "cancelled":
            continue
        side = "sell" if t.side == "sell" else "buy"
        out.append(TickerTrade(
            day=t.filled_at.date(), side=side, quantity=t.quantity, price=t.fill_price, currency="ARS", simulated=True,
        ))
        if t.side == "buy" and t.exit_price is not None and t.closed_at is not None:
            out.append(TickerTrade(
                day=t.closed_at.date(), side="sell", quantity=t.quantity, price=t.exit_price, currency="ARS", simulated=True,
            ))
    return out


def adjust_for_splits(trades: list[TickerTrade], raw: list[DailyBar], adjusted: list[DailyBar]) -> list[TickerTrade]:
    """Restate trades from before a split in today's units, like the chart's prices: 5 at 82.750
    before a 10:1 split reads 50 at 8.275."""
    out = []
    for t in trades:
        pair = next(((r, a) for r, a in zip(raw, adjusted) if r.day >= t.day), None)
        factor = pair[1].close / pair[0].close if pair and pair[0].close else 1.0
        if abs(factor - 1) < 1e-6:
            out.append(t)
        else:
            out.append(t.model_copy(update={"price": t.price * factor, "quantity": t.quantity / factor, "split_adjusted": True}))
    return out


def _asset(o: Trade) -> str:
    """The asset an operation is on: a dollar species counts as its peso ticker."""
    if o.currency == "USD":
        for suffix in (".D", ".C", "D", "C"):
            if o.symbol.endswith(suffix):
                return o.symbol[: -len(suffix)]
    return o.symbol


def _rate_on(day: date, mep: dict[date, float]) -> float | None:
    """That day's MEP rate, or the closest before it; the first known for older days, since IOL's
    history only goes back a year."""
    if not mep:
        return None
    before = [d for d in mep if d <= day]
    return mep[max(before)] if before else mep[min(mep)]


def real_operations(ops: list[Trade], mep: dict[date, float]) -> OperationsOut:
    """Each sell's result against the average cost, in pesos with dollars at that day's MEP rate
    and without fees. It's how IOL gets the cost Mi cartera shows (on 2026-11-02 they matched on
    half the positions and differed under 0.15% on the rest). A sell of more than the known
    history bought has no result."""
    done = [o for o in ops if o.type in SIDES and o.status == "completed" and o.executed and o.executed.qty > 0]
    held: dict[str, float] = defaultdict(float)
    cost: dict[str, float] = defaultdict(float)
    out = []
    for o in sorted(done, key=lambda o: o.execution_date or o.order_date):
        e = o.executed
        assert e is not None
        when = o.execution_date or o.order_date
        asset = _asset(o)
        rate = _rate_on(when.date(), mep)
        pesos = e.amount if o.currency != "USD" else e.amount * rate if rate else None
        result = sold_cost = None
        if SIDES[o.type] == "buy":
            held[asset] += e.qty
            cost[asset] += pesos or 0.0
        elif e.qty > held[asset] + 1e-6:
            held[asset] = cost[asset] = 0.0
        else:
            sold_cost = cost[asset] * e.qty / held[asset]
            result = round(pesos - sold_cost, 2) if pesos is not None else None
            held[asset] -= e.qty
            cost[asset] -= sold_cost
        out.append(_operation(o, asset, when, "completed", e.qty, e.price, e.amount, rate, result, sold_cost))
    for o in ops:
        if o.type in SIDES and o.status == "pending":
            asked = o.order
            qty, price = (asked.qty, asked.price) if asked else (0.0, 0.0)
            amount = (asked.amount or qty * price) if asked else 0.0
            out.append(_operation(o, _asset(o), o.order_date, "pending", qty, price, amount, _rate_on(o.order_date.date(), mep)))
    out.sort(key=lambda x: x.at, reverse=True)
    return OperationsOut(operations=out, realized=round(sum(x.result or 0.0 for x in out), 2))


def _operation(
    o: Trade, asset: str, when: datetime, status: Literal["completed", "pending"], qty: float, price: float, amount: float,
    rate: float | None, result: float | None = None, cost: float | None = None,
) -> Operation:
    return Operation(
        id=str(o.order_id), at=when.replace(tzinfo=market_hours.ART), side=SIDES[o.type], ticker=asset, status=status,
        quantity=qty, price=price, currency="USD" if o.currency == "USD" else "ARS", amount=amount, result=result,
        cost=round(cost, 2) if cost is not None and result is not None else None, rate=rate,
    )


def operations() -> OperationsOut:
    """Every real buy and sell, from the first one."""
    today = market_hours.now_art().date()
    ops = get_iol().operations(FIRST_DAY, today)
    try:
        days = get_iol().account_history(today - timedelta(days=364), today - timedelta(days=1)).history
    except Exception:
        log.warning("no MEP rates for the operations' results")
        days = []
    return real_operations(ops, {d.date: d.exchange_rate.mep for d in days if d.exchange_rate.mep > 0})


def ticker_trades(ticker: str) -> list[TickerTrade]:
    """Oldest first, within the last HISTORY_DAYS (the longest the price chart goes back)."""
    today = date.today()
    start = today - timedelta(days=HISTORY_DAYS)
    simulated = rows_as(TradeRow, get_db().table("trade_intents").select("*").eq("ticker", ticker).execute().data)
    trades = from_operations(get_iol().operations(start, today), ticker) + from_simulated(simulated)
    trades = sorted((t for t in trades if t.day >= start), key=lambda t: t.day)
    if not trades:
        return []
    try:
        days = HISTORY_DAYS + 7
        return adjust_for_splits(trades, prices.daily_bars(ticker, days=days, adjust=False), prices.daily_bars(ticker, days=days))
    except Exception:
        log.warning("no price history to adjust the trades of %s for splits", ticker)
        return trades
