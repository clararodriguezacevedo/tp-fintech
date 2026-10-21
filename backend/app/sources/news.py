"""Recent news from RSS feeds and GDELT."""

import hashlib
from datetime import datetime, timezone
from time import mktime

import feedparser
import httpx

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


def fetch_rss(client: httpx.Client) -> list[dict]:
    out = []
    for source, url in RSS_FEEDS.items():
        try:
            r = client.get(url, headers=HEADERS)
            r.raise_for_status()
        except httpx.HTTPError:
            continue
        for e in feedparser.parse(r.content).entries:
            published = e.get("published_parsed") or e.get("updated_parsed")
            out.append(
                {
                    "external_id": _id(e.link),
                    "source": source,
                    "title": e.title,
                    "summary": e.get("summary", "")[:1000],
                    "url": e.link,
                    "published_at": (
                        datetime.fromtimestamp(mktime(published), tz=timezone.utc).isoformat()
                        if published
                        else None
                    ),
                }
            )
    return out


def fetch_gdelt(client: httpx.Client, timespan: str = "1h") -> list[dict]:
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
    )
    # GDELT answers rate-limited calls with a 200 and a plain-text body.
    if "json" not in r.headers.get("content-type", ""):
        return []
    out = []
    for a in r.json().get("articles", []):
        seen = datetime.strptime(a["seendate"], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        out.append(
            {
                "external_id": _id(a["url"]),
                "source": a.get("domain", "gdelt"),
                "title": a["title"],
                "summary": "",
                "url": a["url"],
                "published_at": seen.isoformat(),
            }
        )
    return out


def fetch_all(client: httpx.Client) -> list[dict]:
    items = {n["external_id"]: n for n in fetch_rss(client) + fetch_gdelt(client)}
    return list(items.values())
