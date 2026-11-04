"""Ask IOL again for the daily candles stored from a date on. Only touches the cache of prices.

Usage (from backend/): uv run python -m scripts.refresh_bars 2026-11-02
"""

import sys
from datetime import date

from app import prices


def main(start: date) -> None:
    tickers, changed = prices.refetch_from(start)
    print(f"{tickers} tickers asked again, {changed} candles changed")


if __name__ == "__main__":
    main(date.fromisoformat(sys.argv[1]))
