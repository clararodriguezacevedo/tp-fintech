"""Recent news from RSS feeds and GDELT."""

import hashlib
import logging
from datetime import datetime, timezone
from time import mktime

import feedparser
import httpx

from app.models.domain import NewsRecord
from app.models.gdelt import ArtList

log = logging.getLogger(__name__)

RSS_FEEDS = {
    "ambito": "https://www.ambito.com/rss/pages/economia.xml",
    "infobae": "https://www.infobae.com/arc/outboundfeeds/rss/category/economia/",
    "lanacion": "https://www.lanacion.com.ar/arc/outboundfeeds/rss/category/economia/",
    "marketwatch": "https://feeds.content.dowjones.io/public/rss/mw_topstories",
}

# GDELT allows one request every 5 seconds, so we send a single combined query per cycle.
GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
GDELT_QUERY = (
    '(merval OR "banco central" OR BCRA OR FMI OR inflación OR YPF OR "Galicia" '
    'OR "Mercado Libre" OR Vista OR Pampa) sourcecountry:AR'
)

HEADERS = {"User-Agent": "Mozilla/5.0 (uni project portfolio advisor)"}


def _id(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()


def fetch_rss(client: httpx.Client) -> list[NewsRecord]:
    out = []
    for source, url in RSS_FEEDS.items():
        try:
            r = client.get(url, headers=HEADERS)
            r.raise_for_status()
        except httpx.HTTPError:
            continue
        for e in feedparser.parse(r.content).entries:
            link, title = e.get("link"), e.get("title")
            if not isinstance(link, str) or not isinstance(title, str):
                continue
            published = e.get("published_parsed") or e.get("updated_parsed")
            out.append(NewsRecord(
                external_id=_id(link),
                source=source,
                title=title,
                summary=str(e.get("summary", ""))[:1000],
                url=link,
                published_at=(
                    datetime.fromtimestamp(mktime(published), tz=timezone.utc)  # type: ignore[arg-type]
                    if published else None
                ),
            ))
    return out


GDELT_TIMEOUT = 12  # seconds; it often takes 10+ and sometimes never answers


def fetch_gdelt(client: httpx.Client, timespan: str = "1h") -> list[NewsRecord]:
    """Never raises: GDELT rate-limits (429), times out and sometimes answers with broken JSON,
    and none of that should stop the RSS news from being saved."""
    try:
        return _fetch_gdelt(client, timespan)
    except (httpx.HTTPError, ValueError) as e:  # ValueError covers bad JSON and validation errors
        log.warning("GDELT unavailable: %s", type(e).__name__)
        return []


def _fetch_gdelt(client: httpx.Client, timespan: str) -> list[NewsRecord]:
    r = client.get(
        GDELT_URL,
        params={
            "query": GDELT_QUERY,
            "mode": "artlist",
            "format": "json",
            "timespan": timespan,
            "maxrecords": 75,
            "sort": "datedesc",
        },
        headers=HEADERS,
        timeout=GDELT_TIMEOUT,
    )
    # GDELT answers rate-limited calls with a plain-text body (sometimes with a 200).
    if "json" not in r.headers.get("content-type", ""):
        return []
    return [
        NewsRecord(
            external_id=_id(a.url),
            source=a.domain or "gdelt",
            title=a.title,
            url=a.url,
            published_at=a.seendate,
        )
        for a in ArtList.model_validate(r.json()).articles
    ]


def fetch_all(client: httpx.Client) -> list[NewsRecord]:
    items = {n.external_id: n for n in fetch_rss(client) + fetch_gdelt(client)}
    return list(items.values())
