"""Move the data to the second model, once the migration is applied and the code deployed.

Asks IOL again for the candles stored before their day had closed (from 2026-11-02 the session
ends at 18:00, not 17:00), marks the last days' news and markets as untagged, so the cycles tag them
again with the new questions (the old tags stay, marked as the first model's), and re-grades every
recommendation against its class.

Usage (from backend/): uv run python -m scripts.start_model_v2 [days]
"""

import sys
from datetime import date, datetime, timedelta, timezone

from app import prices
from app.analysis import track_record
from app.db import get_db


HOURS_CHANGED = date(2026, 11, 2)


def main(days: int = 5) -> None:
    tickers, changed = prices.refetch_from(HOURS_CHANGED)
    print(f"candles asked again: {tickers} tickers, {changed} changed")
    db = get_db()
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    news = db.table("news_items").update({"tagged_at": None}).gte("published_at", since).execute().data
    markets = db.table("prediction_markets").update({"tagged_at": None}).gte("updated_at", since).execute().data
    print(f"to tag again: {len(news)} news, {len(markets)} markets")
    print(f"re-graded: {track_record.regrade_all()}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 5)
