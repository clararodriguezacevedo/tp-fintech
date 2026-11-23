"""Whether the ranking says anything. Each day, from the open to the close, in excess of the median
of each asset's class:

  spread   the top 20% of recommendations by score against the bottom 20%
  top      the top 20% alone, which is all the app can do (there's no short selling). The page takes
           `cost`, the account's real cost of trading, off it for a buy and a sell.
  placebo  scores shuffled between the tickers of each day: if the real spread doesn't beat that,
           it's luck, not the signal
"""

import random
import statistics
from collections import defaultdict
from collections.abc import Callable
from datetime import date

from pydantic import BaseModel

from app import prices
from app.analysis import simulation, track_record
from app.brokers.iol import trade_cost_rate
from app.models.db import RecommendationRow
from app.models.iol import DailyBar

SHARE = 0.2
MIN_PER_DAY = 10  # fewer than this on a day doesn't make a ranking
PLACEBO_RUNS = 300
MIN_SESSIONS = 20  # below this, the page says it's too early to conclude


class Placebo(BaseModel):
    mean_bp: float
    share_at_least_real: float  # how often it did as well as the real thing, by chance


class SignalTest(BaseModel):
    model_version: int
    sessions: int
    recommendations: int
    enough: bool  # sessions >= MIN_SESSIONS
    spread_bp: float | None  # top minus bottom, before costs
    top_bp: float | None  # the top alone, before costs
    placebo: Placebo | None  # scores shuffled between the tickers of each day
    cost: float | None = None  # the account's cost of one operation (a buy or a sell), as a share


Scores = dict[str, float]


def spread(rows: list[RecommendationRow], returns: dict[str, float], scores: Scores) -> tuple[float, float, int] | None:
    """(top minus bottom, top alone, days), averaged over days, in fractions."""
    by_day: dict[date, list[tuple[float, float]]] = defaultdict(list)
    for r in rows:
        if r.id in returns and r.id in scores:
            by_day[r.target_date].append((scores[r.id], returns[r.id]))
    spreads, tops = [], []
    for points in by_day.values():
        if len(points) < MIN_PER_DAY:
            continue
        points.sort(key=lambda p: p[0])
        n = max(1, int(len(points) * SHARE))
        top = statistics.mean(p[1] for p in points[-n:])
        spreads.append(top - statistics.mean(p[1] for p in points[:n]))
        tops.append(top)
    if not spreads:
        return None
    return statistics.mean(spreads), statistics.mean(tops), len(spreads)


def in_excess(rows: list[RecommendationRow], raw: dict[str, float]) -> dict[str, float]:
    """Each return minus the median of its class that day."""
    groups: dict[tuple[date, str], list[RecommendationRow]] = defaultdict(list)
    for r in rows:
        if r.id in raw:
            groups[(r.target_date, track_record.asset_class(r))].append(r)
    out: dict[str, float] = {}
    for rs in groups.values():
        if len(rs) >= track_record.MIN_IN_CLASS:
            median = statistics.median(raw[r.id] for r in rs)
            out.update({r.id: raw[r.id] - median for r in rs})
    return out


def forward_returns(rows: list[RecommendationRow], bars_of: Callable[[str], list[DailyBar]], days: int) -> dict[str, float]:
    """From the open of the target day to the close `days` sessions later (1: the same day)."""
    out: dict[str, float] = {}
    for r in rows:
        bars = [b for b in bars_of(r.ticker) if b.close > 0]
        i = next((k for k, b in enumerate(bars) if b.day == r.target_date), None)
        if i is None or i + days - 1 >= len(bars):
            continue
        b = bars[i]
        if b.open > 0 and b.low <= b.open <= b.high:  # IOL sometimes repeats the last close as the open
            out[r.id] = bars[i + days - 1].close / b.open - 1
    return out


def _shuffled(rows: list[RecommendationRow], key: Callable[[RecommendationRow], object], rng: random.Random) -> Scores:
    groups: dict[object, list[RecommendationRow]] = defaultdict(list)
    for r in rows:
        groups[key(r)].append(r)
    out: Scores = {}
    for rs in groups.values():
        values = [r.score for r in rs]
        rng.shuffle(values)
        out.update({r.id: v for r, v in zip(rs, values)})
    return out


def _placebo(rows, returns, key, real: float, rng: random.Random, runs: int) -> Placebo | None:
    results = [s[0] for _ in range(runs) if (s := spread(rows, returns, _shuffled(rows, key, rng)))]
    if not results:
        return None
    return Placebo(
        mean_bp=round(statistics.mean(results) * 1e4, 1),
        share_at_least_real=round(sum(x >= real for x in results) / len(results), 3),
    )


def check_signal(
    rows: list[RecommendationRow], bars_of: Callable[[str], list[DailyBar]], version: int, runs: int = PLACEBO_RUNS,
) -> SignalTest:
    scores = {r.id: r.score for r in rows}
    returns = in_excess(rows, forward_returns(rows, bars_of, 1))
    sessions = len({r.target_date for r in rows})
    real = spread(rows, returns, scores)
    if real is None:
        return SignalTest(
            model_version=version, sessions=sessions, recommendations=len(rows), enough=False,
            spread_bp=None, top_bp=None, placebo=None,
        )
    rng = random.Random(0)  # the same numbers each time, for the same data
    return SignalTest(
        model_version=version, sessions=sessions, recommendations=len(rows), enough=sessions >= MIN_SESSIONS,
        spread_bp=round(real[0] * 1e4, 1), top_bp=round(real[1] * 1e4, 1),
        placebo=_placebo(rows, returns, lambda r: r.target_date, real[0], rng, runs),
    )


def run() -> list[SignalTest]:
    """One test per model version, newest first: they aren't the same model."""
    rows = track_record.graded_daily()
    versions: dict[int, list[RecommendationRow]] = defaultdict(list)
    for r in rows:
        versions[r.model_version].append(r)
    cache: dict[str, list[DailyBar]] = {}

    def bars_of(ticker: str) -> list[DailyBar]:
        if ticker not in cache:
            try:
                first = min(r.target_date for r in rows)
                cache[ticker] = prices.daily_bars(ticker, days=(date.today() - first).days + 7)
            except Exception:
                cache[ticker] = []
        return cache[ticker]

    real_rate = trade_cost_rate()
    cost = simulation.COMMISSION if real_rate is None else real_rate
    return [check_signal(versions[v], bars_of, v).model_copy(update={"cost": cost}) for v in sorted(versions, reverse=True)]
