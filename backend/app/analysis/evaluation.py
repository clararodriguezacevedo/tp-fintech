"""Whether the ranking says anything, tested the way the papers do before believing a backtest.

Each day, the top 20% of recommendations by score against the bottom 20%, in excess of the median
of their asset class, from that day's open:

  horizons  to the close of that day, the next and the one after. The signal should fade, not grow.
  costs     the top 20% alone (there's no short selling here), minus a round trip of 5, 10 and 20 bp
  reaction  the same ranking on the gap from the previous close to the open, which can't be traded
  placebos  scores shuffled between tickers of a day, and between days of a ticker: if the real
            result doesn't beat them, it's not the signal. Reversing the signs has to flip it.
  delay     the score of the session before: if it does as well, the score isn't using anything new
"""

import random
import statistics
from collections import defaultdict
from collections.abc import Callable
from datetime import date

from pydantic import BaseModel

from app import prices
from app.analysis import track_record
from app.models.db import RecommendationRow
from app.models.iol import DailyBar

SHARE = 0.2
MIN_PER_DAY = 10  # fewer than this on a day doesn't make a ranking
HORIZONS = (1, 2, 3)
COSTS_BP = (5, 10, 20)
PLACEBO_RUNS = 300
MIN_SESSIONS = 20  # below this, the page says it's too early to conclude


class HorizonResult(BaseModel):
    days: int  # 1: that day's close
    sessions: int
    spread_bp: float  # top minus bottom, before costs
    top_bp: float  # the top alone, before costs
    top_net_bp: dict[str, float]  # after a round trip of that many bp


class Placebo(BaseModel):
    mean_bp: float
    share_at_least_real: float  # how often it did as well as the real thing, by chance


class SignalTest(BaseModel):
    model_version: int
    sessions: int
    recommendations: int
    enough: bool  # sessions >= MIN_SESSIONS
    horizons: list[HorizonResult]
    reaction_bp: float | None  # same ranking on the overnight gap: can't be traded
    placebo_tickers: Placebo | None
    placebo_dates: Placebo | None
    inverted_bp: float | None
    delayed_bp: float | None  # yesterday's score on today's move


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


def overnight_returns(rows: list[RecommendationRow]) -> dict[str, float]:
    """The gap to the open: close -> close over open -> close."""
    return {
        r.id: (1 + r.close_return) / (1 + r.realized_return) - 1
        for r in rows if r.close_return is not None and r.realized_return is not None and r.realized_return > -1
    }


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


def _previous_scores(rows: list[RecommendationRow]) -> Scores:
    per_ticker: dict[str, list[RecommendationRow]] = defaultdict(list)
    for r in rows:
        per_ticker[r.ticker].append(r)
    out: Scores = {}
    for rs in per_ticker.values():
        rs.sort(key=lambda r: r.target_date)
        out.update({b.id: a.score for a, b in zip(rs, rs[1:])})
    return out


def check_signal(
    rows: list[RecommendationRow], bars_of: Callable[[str], list[DailyBar]], version: int, runs: int = PLACEBO_RUNS,
) -> SignalTest:
    scores = {r.id: r.score for r in rows}
    horizons = []
    first: dict[str, float] = {}
    for days in HORIZONS:
        returns = in_excess(rows, forward_returns(rows, bars_of, days))
        if days == 1:
            first = returns
        s = spread(rows, returns, scores)
        if s:
            horizons.append(HorizonResult(
                days=days, sessions=s[2], spread_bp=round(s[0] * 1e4, 1), top_bp=round(s[1] * 1e4, 1),
                top_net_bp={str(c): round(s[1] * 1e4 - c, 1) for c in COSTS_BP},
            ))
    sessions = len({r.target_date for r in rows})
    real = spread(rows, first, scores)
    if real is None:
        return SignalTest(
            model_version=version, sessions=sessions, recommendations=len(rows), enough=False, horizons=horizons,
            reaction_bp=None, placebo_tickers=None, placebo_dates=None, inverted_bp=None, delayed_bp=None,
        )
    rng = random.Random(0)  # the same numbers each time, for the same data
    reaction = spread(rows, in_excess(rows, overnight_returns(rows)), scores)
    delayed = spread(rows, first, _previous_scores(rows))
    inverted = spread(rows, first, {k: -v for k, v in scores.items()})
    return SignalTest(
        model_version=version, sessions=sessions, recommendations=len(rows), enough=sessions >= MIN_SESSIONS,
        horizons=horizons,
        reaction_bp=round(reaction[0] * 1e4, 1) if reaction else None,
        placebo_tickers=_placebo(rows, first, lambda r: r.target_date, real[0], rng, runs),
        placebo_dates=_placebo(rows, first, lambda r: r.ticker, real[0], rng, runs),
        inverted_bp=round(inverted[0] * 1e4, 1) if inverted else None,
        delayed_bp=round(delayed[0] * 1e4, 1) if delayed else None,
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

    return [check_signal(versions[v], bars_of, v) for v in sorted(versions, reverse=True)]
