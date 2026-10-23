"""What the user's portfolio would be worth had they followed every daily recommendation.

Day by day, starting from the real portfolio of the day each batch of recommendations was made:

  without following  every position earns its own next-day move (realized_return)
  following          positions marked "sell" are sold at the close and sit in cash for the day;
                     every "buy" gets BUY_ALLOCATION of the portfolio, taken pro rata from the
                     rest; "keep" changes nothing
  costs              COMMISSION per operation, charged only when something changes versus the
                     previous day (entering or leaving a buy, selling or buying back)

Both values compound from the same starting value, so the difference is the effect of
following the recommendations. Positions without a graded move count as flat.
"""

from collections import defaultdict
from datetime import date, datetime

from pydantic import BaseModel

from app.db import get_db, rows_as
from app.models.db import RecommendationRow

BUY_ALLOCATION = 0.05
COMMISSION = 0.006


class SimDay(BaseModel):
    day: date
    bought: list[str]
    sold: list[str]
    base_return: float
    follow_return: float
    base_value: float
    follow_value: float


class Simulation(BaseModel):
    start_day: date | None
    start_value: float
    base_value: float
    follow_value: float
    buy_allocation: float
    commission: float
    days: list[SimDay]


def _weights_at(when: datetime) -> tuple[float, dict[str, float]]:
    """Total value and per-ticker weights from the last holdings snapshot before `when`
    (or the first one after it, for days before snapshots started)."""
    db = get_db()
    head = (
        db.table("holdings_snapshots").select("captured_at").lte("captured_at", when.isoformat())
        .order("captured_at", desc=True).limit(1).execute().data
    ) or (
        db.table("holdings_snapshots").select("captured_at").gt("captured_at", when.isoformat())
        .order("captured_at").limit(1).execute().data
    )
    if not head:
        return 0.0, {}
    captured = head[0]["captured_at"]  # type: ignore[index]
    rows = db.table("holdings_snapshots").select("ticker,value").eq("captured_at", captured).execute().data
    values = {str(r["ticker"]): float(r["value"]) for r in rows}  # type: ignore[index, arg-type]
    total = sum(values.values())
    return total, ({t: v / total for t, v in values.items()} if total else {})


def simulate() -> Simulation:
    recs = rows_as(
        RecommendationRow,
        get_db().table("recommendations").select("*").eq("kind", "daily")
        .not_.is_("evaluated_at", "null").order("target_date").execute().data,
    )
    by_day: dict[date, list[RecommendationRow]] = defaultdict(list)
    for r in recs:
        by_day[r.target_date].append(r)

    base_value = follow_value = start_value = 0.0
    start_day: date | None = None
    prev_buys: set[str] = set()
    prev_sells: set[str] = set()
    days: list[SimDay] = []

    for day in sorted(by_day):
        batch = by_day[day]
        total, weights = _weights_at(max(r.created_at for r in batch))
        if not weights:
            continue
        if start_day is None:
            start_day, start_value = day, total
            base_value = follow_value = total

        moves = {r.ticker: r.realized_return or 0.0 for r in batch}
        buys = {r.ticker for r in batch if r.action == "buy" and r.ticker not in weights}
        sells = {r.ticker for r in batch if r.action == "sell" and r.ticker in weights}

        base_r = sum(w * moves.get(t, 0.0) for t, w in weights.items())

        # Following: sold weight earns nothing today; buys are funded pro rata from the rest.
        kept_r = base_r - sum(weights[t] * moves.get(t, 0.0) for t in sells)
        invested = BUY_ALLOCATION * len(buys)
        follow_r = (1 - invested) * kept_r + sum(BUY_ALLOCATION * moves.get(t, 0.0) for t in buys)

        # Commissions only on changes versus yesterday.
        trades = (
            BUY_ALLOCATION * (len(buys - prev_buys) + len(prev_buys - buys))
            + sum(weights.get(t, 0.0) for t in sells ^ prev_sells)
        )
        follow_r -= trades * COMMISSION

        base_value *= 1 + base_r
        follow_value *= 1 + follow_r
        days.append(SimDay(
            day=day, bought=sorted(buys), sold=sorted(sells), base_return=round(base_r, 6),
            follow_return=round(follow_r, 6), base_value=round(base_value, 2),
            follow_value=round(follow_value, 2),
        ))
        prev_buys, prev_sells = buys, sells

    return Simulation(
        start_day=start_day, start_value=round(start_value, 2), base_value=round(base_value, 2),
        follow_value=round(follow_value, 2), buy_allocation=BUY_ALLOCATION, commission=COMMISSION,
        days=days,
    )
