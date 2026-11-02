"""Every buy and sell of one ticker, for marking them on its price chart.

Real ones come from IOL's operations and simulated ones from trade_intents. A ticker's dollar
species is the same asset bought with dollars (VISTD and VISTC for VIST, AO27D for AO27), so
those count too, in the currency they were traded in.
"""

import logging
from datetime import date, timedelta

from app import prices
from app.brokers.iol import get_iol
from app.db import get_db, rows_as
from app.models.db import TradeRow
from app.models.iol import DailyBar, Trade
from app.schemas import TickerTrade

log = logging.getLogger(__name__)

SIDES = {"Compra": "buy", "Venta": "sell"}
HISTORY_DAYS = 365


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
        if t.fill_price is None or t.filled_at is None:
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
