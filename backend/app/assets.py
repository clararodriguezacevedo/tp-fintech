"""What kind of asset each ticker is (ACCIONES, CEDEARS, TIT. PUBLICOS...), from IOL.

The user's holdings already carry it; anything else is asked to IOL once and cached in
asset_types, since it doesn't change.
"""

import logging

from app.brokers.iol import get_iol
from app.db import get_db
from app.portfolio import get_holdings

log = logging.getLogger(__name__)


def asset_types(tickers: set[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        out |= {h.ticker: h.type for h in get_holdings() if h.ticker in tickers}
    except Exception:
        log.warning("no holdings for asset types")
    missing = sorted(tickers - set(out))
    for i in range(0, len(missing), 100):
        rows = get_db().table("asset_types").select("ticker,asset_type").in_("ticker", missing[i : i + 100]).execute().data
        out |= {str(r["ticker"]): str(r["asset_type"]) for r in rows}  # type: ignore[index]
    fetched = []
    for t in sorted(tickers - set(out)):
        try:
            data = get_iol()._request("GET", f"/broker/assets/{t}", params={"market": "BCBA"})
            kind = str((data or {}).get("asset_type") or "")  # type: ignore[union-attr]
        except Exception:
            log.warning("no asset type for %s", t)
            continue
        if kind:
            out[t] = kind
            fetched.append({"ticker": t, "asset_type": kind})
    if fetched:
        get_db().table("asset_types").upsert(fetched).execute()
    return out
