"""Backtest the trend signal on real price history.

Every day, computes the trend signal with only what was known at that close, and checks it
against the next day's open -> close move (what someone following it could actually get).

Usage (from backend/): uv run python -m scripts.backtest_trend [days]
"""

import math
import sys
from dataclasses import dataclass, field

from app import prices
from app.analysis.scoring import BUY_THRESHOLD, trend_score
from app.analysis.tagger import UNIVERSE


@dataclass
class Bucket:
    moves: list[float] = field(default_factory=list)

    def line(self, label: str, expect_up: bool | None) -> str:
        n = len(self.moves)
        if not n:
            return f"  {label:28} sin casos"
        avg = sum(self.moves) / n
        if expect_up is None:
            right = sum(1 for m in self.moves if abs(m) < 0.015)
            what = "se movió menos de 1,5%"
        else:
            right = sum(1 for m in self.moves if (m > 0) == expect_up)
            what = "subió" if expect_up else "bajó"
        return f"  {label:28} {n:5} casos | {what} {right / n:5.1%} | promedio día siguiente {avg:+.3%}"


def main(days: int) -> None:
    tickers = UNIVERSE["acciones"] + UNIVERSE["cedears"]
    up, down, flat, all_pairs = Bucket(), Bucket(), Bucket(), []
    for t in tickers:
        try:
            bars = [b for b in prices.daily_bars(t, days=days) if b.close > 0 and b.open > 0]
        except Exception as e:
            print(f"  {t}: sin historia ({str(e)[:60]})")
            continue
        for i in range(21, len(bars) - 1):
            signal = trend_score(bars[: i + 1], bars[i].close)
            nxt = bars[i + 1]
            move = nxt.close / nxt.open - 1
            all_pairs.append((signal, move))
            (up if signal >= BUY_THRESHOLD else down if signal <= -BUY_THRESHOLD else flat).moves.append(move)
        print(f"  {t}: {max(len(bars) - 22, 0)} días")

    n = len(all_pairs)
    hits = sum(1 for s, m in all_pairs if (s > 0) == (m > 0))
    mx = sum(s for s, _ in all_pairs) / n
    my = sum(m for _, m in all_pairs) / n
    cov = sum((s - mx) * (m - my) for s, m in all_pairs)
    corr = cov / math.sqrt(sum((s - mx) ** 2 for s, _ in all_pairs) * sum((m - my) ** 2 for _, m in all_pairs))
    print(f"\nTendencia, {len(tickers)} tickers, {n} días-ticker, medido apertura -> cierre del día siguiente")
    print(f"  dirección correcta (signo de la señal) {hits / n:.1%}  | correlación señal/movimiento {corr:+.3f}")
    print(up.line(f"señal >= +{BUY_THRESHOLD} (sube)", True))
    print(down.line(f"señal <= -{BUY_THRESHOLD} (baja)", False))
    print(flat.line("entre medio", None))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 180)
