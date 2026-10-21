"""One-click buys with stop loss and take profit.

With IOL_LIVE_TRADING=false (the default) everything is simulated: fills and exits happen at
the real last price from IOL, and the result is stored in trade_intents. With it on, the same
flow sends real orders to IOL.

Lifecycle: queued (market closed) -> filled -> stopped_out | took_profit | closed (manual).
"""

import logging
from collections.abc import Callable
from datetime import datetime, timezone

from app.analysis import market_hours
from app.brokers.iol import get_iol
from app.config import get_settings
from app.db import get_db

log = logging.getLogger(__name__)

OPEN_STATUSES = ("queued", "filled")

PriceFn = Callable[[str, str], float]


def last_price(ticker: str, market: str = "bCBA") -> float:
    return float(get_iol().quote(ticker, market)["ultimoPrecio"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _update(trade_id: str, **fields) -> dict:
    fields["updated_at"] = _now()
    return get_db().table("trade_intents").update(fields).eq("id", trade_id).execute().data[0]


def _fill(trade: dict, price: float) -> dict:
    live = get_settings().iol_live_trading
    fields = {"status": "filled", "fill_price": price, "filled_at": _now(), "live": live}
    if live:
        order = get_iol().buy(trade["ticker"], trade["quantity"], price, trade["market"])
        fields["iol_order_number"] = order.get("numeroOperacion")
    return _update(trade["id"], **fields)


def _close(trade: dict, price: float, status: str) -> dict:
    if trade["live"]:
        order = get_iol().sell(trade["ticker"], trade["quantity"], price, trade["market"])
        exit_number = order.get("numeroOperacion")
    else:
        exit_number = None
    pnl = (price - float(trade["fill_price"])) * trade["quantity"]
    return _update(
        trade["id"], status=status, exit_price=price, closed_at=_now(),
        realized_pnl=round(pnl, 2), exit_order_number=exit_number,
    )


def create_buy(
    ticker: str,
    quantity: int,
    stop_loss: float,
    take_profit: float,
    recommendation_id: str | None = None,
    market: str = "bCBA",
    price_fn: PriceFn = last_price,
    is_open: Callable[[], bool] = market_hours.is_open,
) -> dict:
    """Record the buy and fill it right away if BYMA is open; otherwise it waits in the queue."""
    ticker = ticker.upper()
    entry = price_fn(ticker, market)
    if not stop_loss < entry < take_profit:
        raise ValueError(
            f"need stop_loss < price < take_profit, got {stop_loss} < {entry} < {take_profit}"
        )
    trade = get_db().table("trade_intents").insert({
        "ticker": ticker,
        "market": market,
        "quantity": quantity,
        "entry_price": entry,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "recommendation_id": recommendation_id,
        "live": get_settings().iol_live_trading,
    }).execute().data[0]
    if is_open():
        trade = _fill(trade, entry)
    return trade


def close_trade(trade_id: str, price_fn: PriceFn = last_price) -> dict:
    """Sell now at the last price (or cancel, if it never filled)."""
    trade = get_db().table("trade_intents").select("*").eq("id", trade_id).execute().data[0]
    if trade["status"] == "queued":
        return _update(trade_id, status="cancelled", closed_at=_now())
    if trade["status"] != "filled":
        raise ValueError(f"trade is already {trade['status']}")
    return _close(trade, price_fn(trade["ticker"], trade["market"]), "closed")


def check_open_trades(price_fn: PriceFn = last_price) -> list[dict]:
    """Fill queued trades and trigger stop loss / take profit. Runs every minute while open."""
    trades = (
        get_db().table("trade_intents").select("*").in_("status", list(OPEN_STATUSES))
        .execute().data
    )
    changed = []
    prices: dict[tuple[str, str], float] = {}
    for t in trades:
        key = (t["ticker"], t["market"])
        try:
            if key not in prices:
                prices[key] = price_fn(*key)
            price = prices[key]
            if t["status"] == "queued":
                changed.append(_fill(t, price))
            elif price <= float(t["stop_loss"]):
                changed.append(_close(t, price, "stopped_out"))
            elif price >= float(t["take_profit"]):
                changed.append(_close(t, price, "took_profit"))
        except Exception as e:
            log.exception("trade %s failed", t["id"])
            if t["live"]:
                _update(t["id"], status="failed", error=str(e)[:500])
    return changed
