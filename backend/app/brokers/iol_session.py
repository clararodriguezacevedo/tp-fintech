"""Keeps the IOL session (bearer + refresh token) in Supabase's iol_session table.

Without this, every Vercel cold start and every GitHub Actions run would log in to IOL with the
password, dozens of times a day. The table has RLS on and no policies, so only the backend's
service key can read it.
"""

import logging
from datetime import datetime, timezone

from app.brokers.iol import Session
from app.db import get_db

log = logging.getLogger(__name__)


class SupabaseSessionStore:
    def load(self) -> Session | None:
        try:
            rows = get_db().table("iol_session").select("*").eq("id", 1).execute().data
        except Exception:
            log.exception("could not load the IOL session; logging in instead")
            return None
        if not rows:
            return None
        row = rows[0]
        return Session(
            access_token=row["access_token"],  # type: ignore[index]
            refresh_token=row["refresh_token"],  # type: ignore[index]
            expires_at=datetime.fromisoformat(str(row["expires_at"])).timestamp(),  # type: ignore[index]
        )

    def save(self, session: Session) -> None:
        try:
            get_db().table("iol_session").upsert({
                "id": 1,
                "access_token": session.access_token,
                "refresh_token": session.refresh_token,
                "expires_at": datetime.fromtimestamp(session.expires_at, tz=timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
        except Exception:
            # Not fatal: the next process just logs in again.
            log.exception("could not save the IOL session")
