"""Implied dollar rates and CEDEAR move decomposition, phrased for the user."""


def implied_rate(peso_price: float, dollar_price: float) -> float:
    """Same bond quoted in pesos and in dollars: AL30 / AL30D gives MEP, AL30 / AL30C gives CCL."""
    return peso_price / dollar_price


def gap(rate: float, official: float) -> float:
    """Brecha versus the official rate, as a fraction."""
    return rate / official - 1


def split_cedear_move(cedear_change: float, fx_change: float) -> dict:
    """Split a CEDEAR's peso return into the underlying stock's move and the dollar's move.

    (1 + cedear) = (1 + stock) * (1 + fx), so stock = (1 + cedear) / (1 + fx) - 1.
    """
    stock_change = (1 + cedear_change) / (1 + fx_change) - 1
    return {
        "total": cedear_change,
        "stock": stock_change,
        "dollar": fx_change,
        "explanation": _explain(cedear_change, stock_change, fx_change),
    }


def _pct(x: float) -> str:
    return f"{x * 100:+.1f}%"


def _explain(total: float, stock: float, fx: float) -> str:
    text = f"En pesos se movió {_pct(total)}: la acción {_pct(stock)} y el dólar CCL {_pct(fx)}."
    if abs(fx) > abs(stock):
        text += " La mayor parte del movimiento es por el dólar, no por la empresa."
    return text
