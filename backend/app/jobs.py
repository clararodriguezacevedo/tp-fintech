"""Periodic jobs. APScheduler runs them on a timer inside the FastAPI process (see main.py)."""

import logging
from datetime import datetime, timezone

import httpx

from app.analysis.tagger import tag_items
from app.db import get_db
from app.sources import kalshi, news, polymarket

log = logging.getLogger(__name__)

TAG_BATCH_SIZE = 20


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


SNAPSHOT_MIN_MOVE = 0.005


def _current_probabilities(external_ids: list[str]) -> dict[tuple[str, str], float | None]:
    # Chunked so the PostgREST query string stays short.
    out = {}
    for i in range(0, len(external_ids), 100):
        rows = (
            get_db().table("prediction_markets").select("source,external_id,probability")
            .in_("external_id", external_ids[i : i + 100]).execute().data
        )
        out.update({(r["source"], r["external_id"]): r["probability"] for r in rows})
    return out


def _moved(before, after) -> bool:
    if after is None:
        return False
    if before is None:
        return True
    return abs(float(after) - float(before)) >= SNAPSHOT_MIN_MOVE


def collect_markets() -> None:
    db = get_db()
    with httpx.Client(timeout=30) as client:
        markets = polymarket.fetch_markets(client) + kalshi.fetch_markets(client)
    previous = _current_probabilities([m["external_id"] for m in markets])
    rows = [{**m, "updated_at": _now()} for m in markets]
    saved = (
        db.table("prediction_markets")
        .upsert(rows, on_conflict="source,external_id")
        .execute()
        .data
    )
    # Only snapshot markets whose probability moved, so the free-tier database doesn't fill up
    # with identical rows every 10 minutes.
    changed = [
        r for r in saved
        if _moved(previous.get((r["source"], r["external_id"])), r["probability"])
    ]
    if changed:
        db.table("market_snapshots").insert(
            [{"market_id": r["id"], "probability": r["probability"], "volume_24h": r["volume_24h"]}
             for r in changed]
        ).execute()
    log.info("saved %d markets, %d snapshots", len(saved), len(changed))


def collect_news() -> None:
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        items = news.fetch_all(client)
    if items:
        get_db().table("news_items").upsert(
            items, on_conflict="external_id", ignore_duplicates=True
        ).execute()
    log.info("fetched %d news items", len(items))


def _save_tags(table: str, kind: str, rows: list[dict], text_key: str | None) -> None:
    db = get_db()
    tagged = tag_items(
        [{"id": r["id"], "kind": kind, "title": r["title"], "text": r.get(text_key) or ""}
         for r in rows]
    )
    impacts = []
    for item in tagged:
        db.table(table).update({"ai_summary": item.summary, "tagged_at": _now()}).eq(
            "id", item.id
        ).execute()
        impacts += [
            {"item_kind": kind, "item_id": item.id, **i.model_dump()} for i in item.impacts
        ]
    if impacts:
        db.table("ticker_impacts").insert(impacts).execute()


def tag_pending() -> None:
    """Tag news and markets that haven't been through the LLM yet."""
    db = get_db()
    pending_news = (
        db.table("news_items").select("id,title,summary").is_("tagged_at", "null")
        .order("published_at", desc=True).limit(TAG_BATCH_SIZE).execute().data
    )
    if pending_news:
        _save_tags("news_items", "news", pending_news, "summary")

    pending_markets = (
        db.table("prediction_markets").select("id,title").is_("tagged_at", "null")
        .order("volume_24h", desc=True).limit(TAG_BATCH_SIZE).execute().data
    )
    if pending_markets:
        _save_tags("prediction_markets", "market", pending_markets, None)


def run_cycle() -> None:
    for job in (collect_markets, collect_news, tag_pending):
        try:
            job()
        except Exception:
            log.exception("%s failed", job.__name__)
