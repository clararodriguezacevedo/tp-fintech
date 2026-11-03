from datetime import date, datetime

from app.models.iol import Executed, Trade
from app.trading import history


def _op(id_, day, type_, symbol, qty, amount, currency="ARS", status="completed", order=None):
    when = datetime(2026, 10, day, 12)
    return Trade(
        order_id=id_, order_date=when, execution_date=when if status == "completed" else None, type=type_, status=status,
        symbol=symbol, currency=currency, order=order,
        executed=Executed(qty=qty, price=amount / qty if qty else 0, amount=amount),
    )


def _result(ops, mep=None):
    return history.real_operations(ops, mep or {})


def test_a_sell_counts_against_the_average_cost():
    out = _result([
        _op(1, 1, "Compra", "GGAL", 10, 1000),
        _op(2, 2, "Compra", "GGAL", 10, 2000),
        _op(3, 3, "Venta", "GGAL", 10, 2500),  # average 150: cost 1500
        _op(4, 4, "Venta", "GGAL", 10, 1000),  # the other 1500 stays as its cost
    ])
    assert [(o.id, o.result) for o in out.operations] == [("4", -500.0), ("3", 1000.0), ("2", None), ("1", None)]
    assert out.realized == 500.0


def test_a_dollar_species_is_the_same_asset_at_that_days_mep():
    mep = {date(2026, 10, 1): 1000.0, date(2026, 10, 2): 2000.0}
    out = _result([
        _op(1, 1, "Compra", "VISTD", 2, 100, "USD"),  # $ 100.000
        _op(2, 2, "Venta", "VIST", 1, 60000),  # cost $ 50.000
        _op(3, 3, "Venta", "VISTD", 1, 40, "USD"),  # no rate for the 3rd: the 2nd's, $ 80.000
    ], mep)
    assert {o.ticker for o in out.operations} == {"VIST"}
    assert [o.result for o in out.operations] == [30000.0, 10000.0, None]
    # What the buttons need to show them in the other currency, or as a percentage of the cost.
    assert [(o.cost, o.rate) for o in out.operations] == [(50000.0, 2000.0), (50000.0, 2000.0), (None, 1000.0)]


def test_peso_tickers_ending_in_d_keep_their_name():
    assert _result([_op(1, 1, "Compra", "YPFD", 1, 100)]).operations[0].ticker == "YPFD"
    assert _result([_op(1, 1, "Compra", "BMA.D", 1, 100, "USD")]).operations[0].ticker == "BMA"


def test_selling_more_than_the_history_bought_has_no_result():
    out = _result([_op(1, 1, "Compra", "GGAL", 1, 100), _op(2, 2, "Venta", "GGAL", 5, 900)])
    assert out.operations[0].result is None and out.realized == 0.0


def test_pending_orders_show_without_a_result_and_the_rest_are_left_out():
    asked = Executed(qty=0, price=814, amount=280000)
    out = _result([
        _op(1, 2, "Compra", "ALUA", 0, 0, status="pending", order=asked),
        _op(2, 1, "Compra", "GGAL", 0, 0, status="cancelled"),
        _op(3, 1, "Pago de Dividendos", "GGAL", 1, 10),
    ])
    assert len(out.operations) == 1
    o = out.operations[0]
    assert (o.ticker, o.status, o.price, o.amount, o.result) == ("ALUA", "pending", 814, 280000, None)


def test_a_cancelled_simulated_trade_isnt_marked_on_the_chart():
    from app.models.db import TradeRow

    now = datetime(2026, 11, 2, 19)
    row = TradeRow(
        id="x", ticker="ALUA", market="BCBA", quantity=300, entry_price=814, status="cancelled", live=False,
        fill_price=814, filled_at=now, created_at=now, updated_at=now,
    )
    assert history.from_simulated([row]) == []
