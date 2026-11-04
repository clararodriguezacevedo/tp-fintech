"""Recent news from RSS feeds and GDELT."""

import hashlib
import logging
import re
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


# The general feeds talk about the economy. This is what talks about each company.
GOOGLE_NEWS = "https://news.google.com/rss/search"
PER_COMPANY = 5  # the most recent of each search
COMPANIES_PER_CYCLE = 8  # one request each; at one cycle every 10 minutes, all of them about hourly


def search_name(ticker: str, name: str, aliases: list[str] | None = None) -> str:
    """What the press calls it: the first alias, or the name without its legal ending."""
    if aliases:
        return aliases[0]
    clean = re.sub(r"\b(inc|corp|corporation|ltd|s\.?a\.?|co|plc|n\.?v\.?)\b\.?", "", name, flags=re.IGNORECASE)
    return " ".join(clean.split()) or ticker


def pick_rotation(companies: dict[str, str], now: datetime) -> list[str]:
    """Which companies to search this cycle, taking turns, from nothing but the time."""
    if not companies:
        return []
    names = sorted(companies.values())
    start = (now.hour * 6 + now.minute // 10) * COMPANIES_PER_CYCLE % len(names)
    return (names + names)[start : start + min(COMPANIES_PER_CYCLE, len(names))]


def fetch_company_news(client: httpx.Client, names: list[str]) -> list[NewsRecord]:
    out = []
    for name in names:
        try:
            r = client.get(
                GOOGLE_NEWS, headers=HEADERS,
                params={"q": f'"{name}" when:2d', "hl": "es-419", "gl": "AR", "ceid": "AR:es-419"},
            )
            r.raise_for_status()
        except httpx.HTTPError:
            continue
        entries = feedparser.parse(r.content).entries
        dated = [e for e in entries if e.get("published_parsed")]
        dated.sort(key=lambda e: e["published_parsed"], reverse=True)  # type: ignore[arg-type, return-value]
        for e in dated[:PER_COMPANY]:
            link, title = e.get("link"), e.get("title")
            if not isinstance(link, str) or not isinstance(title, str):
                continue
            source = e.get("source")
            outlet = str(source.get("title", "")) if isinstance(source, dict) else ""
            out.append(NewsRecord(
                external_id=_id(link),
                source=outlet or "google news",
                # Titles end in " - Outlet". Its summary is only links, so it isn't kept.
                title=title.removesuffix(f" - {outlet}") if outlet else title,
                summary="",
                url=link,
                published_at=datetime.fromtimestamp(mktime(e["published_parsed"]), tz=timezone.utc),  # type: ignore[arg-type]
            ))
    return out


def fetch_all(client: httpx.Client, companies: list[str] | None = None) -> list[NewsRecord]:
    items = {
        n.external_id: n
        for n in fetch_rss(client) + fetch_gdelt(client) + fetch_company_news(client, companies or [])
    }
    return list(items.values())
