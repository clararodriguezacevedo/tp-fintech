"""Apply pending SQL files from supabase/migrations, in name order.

Usage (from backend/): uv run python scripts/migrate.py
Needs DATABASE_URL in backend/.env. Applied files are recorded in public.schema_migrations.
"""

from pathlib import Path

import psycopg
from dotenv import dotenv_values

MIGRATIONS = Path(__file__).resolve().parents[2] / "supabase" / "migrations"


def _connect_args(url: str) -> dict:
    """Split postgresql://user:password@host:port/db by hand.

    Supabase passwords often contain characters like / or # that break normal URL parsing,
    so the password is everything between the first ':' after the scheme and the last '@'.
    """
    rest = url.split("://", 1)[1]
    creds, _, location = rest.rpartition("@")
    user, _, password = creds.partition(":")
    hostport, _, dbname = location.partition("/")
    host, _, port = hostport.partition(":")
    return {
        "user": user,
        "password": password,
        "host": host,
        "port": port or "5432",
        "dbname": dbname.split("?", 1)[0] or "postgres",
    }


def main() -> None:
    url = dotenv_values(Path(__file__).resolve().parents[1] / ".env").get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is not set in backend/.env")

    with psycopg.connect(**_connect_args(url)) as conn:
        conn.execute(
            "create table if not exists schema_migrations "
            "(name text primary key, applied_at timestamptz not null default now())"
        )
        conn.execute("alter table schema_migrations enable row level security")
        applied = {r[0] for r in conn.execute("select name from schema_migrations")}

        pending = [f for f in sorted(MIGRATIONS.glob("*.sql")) if f.name not in applied]
        if not pending:
            print("nothing to apply")
        for f in pending:
            # Each file runs in its own transaction, so a failing file leaves nothing half done.
            with conn.transaction():
                conn.execute(f.read_text(encoding="utf-8"))
                conn.execute("insert into schema_migrations (name) values (%s)", (f.name,))
            print(f"applied {f.name}")


if __name__ == "__main__":
    main()
