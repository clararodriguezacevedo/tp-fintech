"""The user's investor profile and where it came from.

IOL keeps the result of its investor test ("test del inversor"), which the CNV requires; the
current IOL API doesn't expose it, so it's read from IOL's previous API (/api/v2/datos-perfil,
same username and password) at most once a day. When IOL has a profile it wins. While IOL's test
is pending, the profile the user declared in the app is used, and with neither, conservador:
the most prudent one.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Literal

import httpx
from pydantic import BaseModel

from app.analysis.suitability import PROFILES, Profile
from app.config import get_settings
from app.db import get_db

log = logging.getLogger(__name__)

LEGACY = "https://api.invertironline.com"
CHECK_EVERY = timedelta(hours=24)


class InvestorProfile(BaseModel):
    profile: Profile
    source: Literal["iol", "declared", "default"]
    iol_test_pending: bool | None = None  # IOL asks the user to take or update its test
    declared: Profile | None = None


def _normalize(value: str | None) -> Profile | None:
    v = (value or "").strip().lower()
    for p in PROFILES:
        if v.startswith(p[:5]):  # "Conservador", "Moderado", "Arriesgado" / "Agresivo"
            return p
    return "arriesgado" if v.startswith("agres") else None


def _fetch_from_iol() -> tuple[str, bool]:
    s = get_settings()
    with httpx.Client(timeout=20) as client:
        token = client.post(f"{LEGACY}/token", data={
            "username": s.iol_username, "password": s.iol_password, "grant_type": "password",
        }).raise_for_status().json()["access_token"]
        data = client.get(f"{LEGACY}/api/v2/datos-perfil", headers={"Authorization": f"Bearer {token}"}).raise_for_status().json()
    # Only these two fields are kept; the rest of the response (name, DNI...) is ignored.
    return str(data.get("perfilInversor") or ""), bool(data.get("actualizarTestInversor"))


def _row() -> dict:
    rows = get_db().table("investor_profile").select("*").eq("id", 1).execute().data
    return dict(rows[0]) if rows else {}  # type: ignore[arg-type]


def get_profile(refresh: bool = False) -> InvestorProfile:
    row = _row()
    checked = row.get("iol_checked_at")
    stale = not checked or datetime.now(timezone.utc) - datetime.fromisoformat(str(checked)) > CHECK_EVERY
    if refresh or stale:
        try:
            iol, pending = _fetch_from_iol()
            get_db().table("investor_profile").upsert({
                "id": 1, "iol": iol, "iol_test_pending": pending,
                "iol_checked_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
            row |= {"iol": iol, "iol_test_pending": pending}
        except Exception:
            log.warning("could not read the investor profile from IOL")
    declared = _normalize(row.get("declared"))
    from_iol = _normalize(row.get("iol"))
    if from_iol:
        return InvestorProfile(profile=from_iol, source="iol", iol_test_pending=row.get("iol_test_pending"), declared=declared)
    if declared:
        return InvestorProfile(profile=declared, source="declared", iol_test_pending=row.get("iol_test_pending"), declared=declared)
    return InvestorProfile(profile="conservador", source="default", iol_test_pending=row.get("iol_test_pending"))


def declare(profile: Profile) -> InvestorProfile:
    get_db().table("investor_profile").upsert({
        "id": 1, "declared": profile, "updated_at": datetime.now(timezone.utc).isoformat(),
    }).execute()
    return get_profile()
