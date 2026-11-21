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
from app.analysis import market_hours, rotation
from app.brokers.iol import get_iol
from app.db import all_rows, get_db, rows_as
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


def simulated_operations(rows: list[TradeRow]) -> list[Operation]:
    """The site's paper trades as operations: a buy, and its sell once it closed. Real orders sent
    from the site are left out, since they already come in IOL's operations."""
    out = []
    for t in rows:
        if t.live or t.status in ("cancelled", "failed"):
            continue
        done = t.fill_price is not None and t.filled_at is not None
        at = t.filled_at if done and t.filled_at else t.created_at
        price = t.fill_price if done and t.fill_price is not None else t.entry_price
        status: Literal["completed", "pending"] = "completed" if done else "pending"
        common = {"ticker": t.ticker, "quantity": float(t.quantity), "currency": "ARS", "source": "simulated"}
        if t.side == "sell":
            out.append(Operation(
                id=f"site-{t.id}", at=at.astimezone(market_hours.ART), side="sell", status=status, price=price,
                amount=price * t.quantity, result=t.realized_pnl, cost=t.cost_basis if t.realized_pnl is not None else None,
                **common,  # type: ignore[arg-type]
            ))
            continue
        out.append(Operation(
            id=f"site-{t.id}", at=at.astimezone(market_hours.ART), side="buy", status=status, price=price,
            amount=price * t.quantity, **common,  # type: ignore[arg-type]
        ))
        if t.exit_price is not None and t.closed_at is not None:
            out.append(Operation(
                id=f"site-{t.id}-exit", at=t.closed_at.astimezone(market_hours.ART), side="sell", status="completed",
                price=t.exit_price, amount=t.exit_price * t.quantity, result=t.realized_pnl,
                cost=round(price * t.quantity, 2) if t.realized_pnl is not None else None, **common,  # type: ignore[arg-type]
            ))
    return out


def mark_plan(ops: list[Operation], recs: dict[date, dict[str, tuple[str, float]]]) -> None:
    """Marks the operations that did what that day's plan said, in any quantity.

    `recs` is each day's batch, ticker to (action, score). A buy follows the plan when the batch
    said buy. A sell does when the batch said sell, or when it pays for a planned buy made the
    same day the way the plan rotates (rotation.build): the buy beats it by ROTATION_GAP or more
    and the sold position wasn't expected to rise."""
    for day in {o.at.date() for o in ops}:
        batch = recs.get(day)
        if not batch:
            continue
        mine = [o for o in ops if o.at.date() == day]

        def score(t: str, batch: dict[str, tuple[str, float]] = batch) -> float:
            return batch[t][1] if t in batch else 0.0  # as the plan reads a missing one

        bought: list[tuple[bool, float]] = []  # a paper sell only pays for a paper buy
        for o in mine:
            if o.side == "buy" and batch.get(o.ticker, ("", 0.0))[0] == "buy":
                o.followed_plan = True
                bought.append((o.source == "simulated", score(o.ticker)))
        for o in mine:
            if o.side != "sell":
                continue
            s = score(o.ticker)
            o.followed_plan = batch.get(o.ticker, ("", 0.0))[0] == "sell" or any(
                paper == (o.source == "simulated") and b - s >= rotation.ROTATION_GAP and s <= rotation.ROTATION_MAX_HELD_SCORE
                for paper, b in bought
            )


def daily_batches(days: set[date]) -> dict[date, dict[str, tuple[str, float]]]:
    """Each day's daily batch, ticker to (action, score)."""
    if not days:
        return {}
    wanted = sorted(d.isoformat() for d in days)
    rows = all_rows(lambda: (
        get_db().table("recommendations").select("ticker,action,score,target_date").eq("kind", "daily")
        .in_("target_date", wanted).order("id")
    ))
    out: dict[date, dict[str, tuple[str, float]]] = defaultdict(dict)
    for r in rows:
        out[date.fromisoformat(str(r["target_date"]))][str(r["ticker"])] = (str(r["action"]), float(r["score"]))
    return out


def operations() -> OperationsOut:
    """Every buy and sell, real from the first one and simulated from the site, newest first."""
    today = market_hours.now_art().date()
    ops = get_iol().operations(FIRST_DAY, today)
    try:
        days = get_iol().account_history(today - timedelta(days=364), today - timedelta(days=1)).history
    except Exception:
        log.warning("no MEP rates for the operations' results")
        days = []
    out = real_operations(ops, {d.date: d.exchange_rate.mep for d in days if d.exchange_rate.mep > 0})
    trades = rows_as(TradeRow, get_db().table("trade_intents").select("*").execute().data)
    sent = {str(n) for t in trades if t.live for n in (t.iol_order_number, t.exit_order_number) if n}
    for o in out.operations:
        if o.id in sent:
            o.source = "site"
    out.operations += simulated_operations(trades)
    out.operations.sort(key=lambda x: x.at, reverse=True)
    try:
        mark_plan(out.operations, daily_batches({o.at.date() for o in out.operations}))
    except Exception:
        log.exception("could not compare the operations with each day's plan")
    return out


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
