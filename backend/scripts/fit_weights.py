"""Suggest score weights from graded recommendations instead of judgment calls.

Fits a logistic regression of "did the price go up from the next open to the close?" on the
score's components (evidence, trend, context, gap), training on the older days and testing on
the most recent ones, so a weight that only fits noise shows up as no better than chance.
Prints suggested weights; it never changes the scoring by itself.

Usage (from backend/): uv run python -m scripts.fit_weights
"""

import math
import random
from collections import defaultdict

from app.db import get_db, rows_as
from app.models.db import RecommendationRow

MIN_ROWS = 300  # below this the weights would mostly reflect noise
TEST_SHARE = 0.25  # most recent days held out
NOISE = 0.001  # moves smaller than 0.1% are neither up nor down
FEATURES = ("evidence", "trend", "context", "gap")


def features(r: RecommendationRow) -> list[float]:
    b = r.signal_breakdown
    return [math.tanh((b.news + b.markets) / 2), b.trend, b.context, b.gap]


def fit(xs: list[list[float]], ys: list[int], l2: float = 0.01, steps: int = 3000, lr: float = 0.1):
    w = [0.0] * len(xs[0])
    bias = 0.0
    for _ in range(steps):
        gw = [0.0] * len(w)
        gb = 0.0
        for x, y in zip(xs, ys):
            p = 1 / (1 + math.exp(-(bias + sum(wi * xi for wi, xi in zip(w, x)))))
            for i, xi in enumerate(x):
                gw[i] += (p - y) * xi
            gb += p - y
        w = [wi - lr * (g / len(xs) + l2 * wi) for wi, g in zip(w, gw)]
        bias -= lr * gb / len(xs)
    return w, bias


def accuracy(w: list[float], bias: float, xs: list[list[float]], ys: list[int]) -> float:
    right = sum(
        1 for x, y in zip(xs, ys) if (bias + sum(wi * xi for wi, xi in zip(w, x)) > 0) == (y == 1)
    )
    return right / len(xs) if xs else 0.0


def main() -> None:
    rows = [
        r for r in rows_as(
            RecommendationRow,
            get_db().table("recommendations").select("*").eq("kind", "daily")
            .not_.is_("realized_return", "null").execute().data,
        )
        if r.realized_return is not None and abs(r.realized_return) >= NOISE
    ]
    days = sorted({r.target_date for r in rows})
    print(f"{len(rows)} graded recommendations over {len(days)} days")
    if len(rows) < MIN_ROWS or len(days) < 8:
        print(f"Not enough yet: need at least {MIN_ROWS} over 8+ days. Keep the current weights.")
        return

    cut = days[int(len(days) * (1 - TEST_SHARE))]
    train = [r for r in rows if r.target_date < cut]
    test = [r for r in rows if r.target_date >= cut]
    xs, ys = [features(r) for r in train], [int(r.realized_return > 0) for r in train]  # type: ignore[operator]
    tx, ty = [features(r) for r in test], [int(r.realized_return > 0) for r in test]  # type: ignore[operator]
    w, bias = fit(xs, ys)

    up_share = sum(ty) / len(ty)
    baseline = max(up_share, 1 - up_share)  # always guessing the more common direction
    print(f"train {len(train)} / test {len(test)} (from {cut})")
    print(f"test accuracy {accuracy(w, bias, tx, ty):.1%} vs {baseline:.1%} always guessing the majority")
    total = sum(abs(x) for x in w) or 1
    print("\nsuggested weights (sign < 0 means the signal works backwards):")
    for name, wi in zip(FEATURES, w):
        print(f"  {name:9} {wi / total:+.2f}")

    # Per-day spread, to see if one day dominates.
    by_day: dict[str, int] = defaultdict(int)
    for r in rows:
        by_day[r.target_date.isoformat()] += 1
    print("\nrows per day:", dict(sorted(by_day.items())))


if __name__ == "__main__":
    random.seed(0)
    main()
