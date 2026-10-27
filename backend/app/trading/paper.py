"""One-click buys with stop loss and take profit.

Paper buys fill immediately at the last price, also outside market hours (the last close);
real buys placed while BYMA is closed wait in the queue for the open.

With IOL_LIVE_TRADING=false (the default) everything is simulated: fills and exits happen at
the real last price from IOL, and the result is stored in trade_intents. With it on, the same
flow sends real orders to IOL.

Lifecycle of a buy: queued (market closed) -> filled -> stopped_out | took_profit | closed (sold
by the user). A sell of a position the user holds (following a "sell" recommendation, say) is
one step: filled at the last price (paper: right away; live: queued while BYMA is closed), with
its result measured against what those units cost. A paper sell doesn't change the IOL account.
"""

import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from app import prices
from app.analysis import market_hours
from app.brokers.iol import get_iol
from app.config import get_settings
from app.db import get_db, rows_as
from app.models.db import TradeRow, TradeStatus

log = logging.getLogger(__name__)

OPEN_STATUSES: list[TradeStatus] = ["queued", "filled"]

PriceFn = Callable[[str, str], float]


def last_price(ticker: str, market: str = "BCBA") -> float:
    """Live price from IOL, or the last close when IOL doesn't answer (it happens at night)."""
    try:
        price = get_iol().quote(ticker, market).price
        if price:
            return price
    except Exception:
        log.warning("no live price for %s; using the last close", ticker)
    bars = prices.daily_bars(ticker)
    if not bars:
        raise ValueError(f"no price available for {ticker}")
    return bars[-1].close


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _update(trade_id: str, **fields: Any) -> TradeRow:
    fields["updated_at"] = _now()
    data = get_db().table("trade_intents").update(fields).eq("id", trade_id).execute().data
    return rows_as(TradeRow, data)[0]


def _get(trade_id: str) -> TradeRow:
    rows = rows_as(TradeRow, get_db().table("trade_intents").select("*").eq("id", trade_id).execute().data)
    if not rows:
        raise ValueError(f"trade {trade_id} not found")
    return rows[0]


def _fill(trade: TradeRow, price: float) -> TradeRow:
    live = get_settings().iol_live_trading
    fields: dict[str, Any] = {"status": "filled", "fill_price": price, "filled_at": _now(), "live": live}
    if live:
        send = get_iol().sell if trade.side == "sell" else get_iol().buy
        fields["iol_order_number"] = send(trade.ticker, trade.quantity, price, trade.market).order_id
    if trade.side == "sell" and trade.cost_basis is not None:
        # The sell's own result: what it brought minus what those units cost.
        fields["realized_pnl"] = round(trade.quantity * price * _unit_factor(trade.ticker) - trade.cost_basis, 2)
        fields["exit_price"] = price
        fields["closed_at"] = _now()
    return _update(trade.id, **fields)


def _unit_factor(ticker: str) -> float:
    """Pesos per unit per peso of price: bonds are quoted per 100 nominal."""
    from app.portfolio import BOND_TYPES, current_holdings  # avoid an import cycle

    holding = next((h for h in current_holdings().holdings if h.ticker == ticker), None)
    return 0.01 if holding and holding.type in BOND_TYPES else 1.0


def sell_plan(ticker: str, price_fn: PriceFn = last_price) -> dict[str, Any]:
    """What selling the position in `ticker` would bring per unit, and what it cost."""
    from app.portfolio import current_holdings  # avoid an import cycle

    ticker = ticker.upper()
    holding = next((h for h in current_holdings().holdings if h.ticker == ticker), None)
    if holding is None or holding.quantity <= 0:
        raise ValueError(f"no tenés {ticker} en tu cartera")
    price = price_fn(ticker, "BCBA")
    value_per_unit = holding.value / holding.quantity * (price / holding.last_price if holding.last_price else 1.0)
    cost_per_unit = (holding.value - holding.gain_amount) / holding.quantity
    return {
        "ticker": ticker, "held": int(holding.quantity), "price": price,
        "value_per_unit": value_per_unit, "cost_per_unit": cost_per_unit,
    }


def _close(trade: TradeRow, price: float, status: TradeStatus) -> TradeRow:
    exit_number = None
    if trade.live:
        exit_number = get_iol().sell(trade.ticker, trade.quantity, price, trade.market).order_id
    assert trade.fill_price is not None, "only filled trades can be closed"
    pnl = (price - trade.fill_price) * trade.quantity
    return _update(
        trade.id, status=status, exit_price=price, closed_at=_now(),
        realized_pnl=round(pnl, 2), exit_order_number=exit_number,
    )


def create_buy(
    ticker: str,
    quantity: int,
    stop_loss: float,
    take_profit: float,
    recommendation_id: str | None = None,
    market: str = "BCBA",
    price_fn: PriceFn = last_price,
    is_open: Callable[[], bool] = market_hours.is_open,
) -> TradeRow:
    """Record the buy and fill it right away if BYMA is open; otherwise it waits in the queue."""
    ticker = ticker.upper()
    if quantity <= 0:
        raise ValueError("quantity must be positive")
    entry = price_fn(ticker, market)
    if not stop_loss < entry < take_profit:
        raise ValueError(
            f"need stop_loss < price < take_profit, got {stop_loss} < {entry} < {take_profit}"
        )
    data = get_db().table("trade_intents").insert({
        "ticker": ticker,
        "market": market,
        "quantity": quantity,
        "entry_price": entry,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "recommendation_id": recommendation_id,
        "live": get_settings().iol_live_trading,
    }).execute().data
    trade = rows_as(TradeRow, data)[0]
    # Paper trades fill right away at the last price, even with the market closed (that price
    # is the last close); real orders wait for the open.
    if is_open() or not get_settings().iol_live_trading:
        trade = _fill(trade, entry)
    return trade


def create_sell(
    ticker: str,
    quantity: int,
    recommendation_id: str | None = None,
    market: str = "BCBA",
    price_fn: PriceFn = last_price,
    is_open: Callable[[], bool] = market_hours.is_open,
) -> TradeRow:
    """Sell `quantity` units of a position the user holds."""
    plan = sell_plan(ticker, price_fn)
    if not 0 < quantity <= plan["held"]:
        raise ValueError(f"podés vender entre 1 y {plan['held']} {plan['ticker']}")
    data = get_db().table("trade_intents").insert({
        "ticker": plan["ticker"],
        "market": market,
        "side": "sell",
        "quantity": quantity,
        "entry_price": plan["price"],
        "cost_basis": round(plan["cost_per_unit"] * quantity, 2),
        "recommendation_id": recommendation_id,
        "live": get_settings().iol_live_trading,
    }).execute().data
    trade = rows_as(TradeRow, data)[0]
    if is_open() or not get_settings().iol_live_trading:
        trade = _fill(trade, plan["price"])
    return trade


def close_trade(trade_id: str, price_fn: PriceFn = last_price) -> TradeRow:
    """Sell now at the last price (or cancel, if it never filled)."""
    trade = _get(trade_id)
    if trade.status == "queued":
        return _update(trade_id, status="cancelled", closed_at=_now())
    if trade.status != "filled" or trade.side == "sell":
        raise ValueError(f"trade is already {trade.status}")
    return _close(trade, price_fn(trade.ticker, trade.market), "closed")


def check_open_trades(price_fn: PriceFn = last_price) -> list[TradeRow]:
    """Fill queued trades and trigger stop loss / take profit. Runs every minute while open."""
    trades = rows_as(
        TradeRow,
        get_db().table("trade_intents").select("*").in_("status", OPEN_STATUSES).execute().data,
    )
    changed = []
    prices: dict[tuple[str, str], float] = {}
    for t in trades:
        key = (t.ticker, t.market)
        try:
            if key not in prices:
                prices[key] = price_fn(*key)
            price = prices[key]
            if t.status == "queued":
                changed.append(_fill(t, price))
            elif t.side == "sell":
                continue
            elif t.stop_loss is not None and price <= t.stop_loss:
                changed.append(_close(t, price, "stopped_out"))
            elif t.take_profit is not None and price >= t.take_profit:
                changed.append(_close(t, price, "took_profit"))
        except Exception as e:
            log.exception("trade %s failed", t.id)
            if t.live:
                _update(t.id, status="failed", error=str(e)[:500])
    return changed
