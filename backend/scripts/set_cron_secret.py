"""Store API_KEY from backend/.env in Supabase Vault as 'api_key', for the pg_cron jobs.

Usage (from backend/): uv run python -m scripts.set_cron_secret
Run it again after changing API_KEY. The value is never printed.
"""

from pathlib import Path

import psycopg
from dotenv import dotenv_values

from scripts.migrate import _connect_args

ENV = Path(__file__).resolve().parents[1] / ".env"


def main() -> None:
    env = dotenv_values(ENV)
    url, key = env.get("DATABASE_URL"), env.get("API_KEY")
    if not url or not key:
        raise SystemExit("DATABASE_URL and API_KEY must be set in backend/.env")
    with psycopg.connect(**_connect_args(url)) as conn:
        existing = conn.execute("select id from vault.secrets where name = 'api_key'").fetchone()
        if existing:
            conn.execute("select vault.update_secret(%s, %s)", (existing[0], key))
            print("updated vault secret 'api_key'")
        else:
            conn.execute("select vault.create_secret(%s, 'api_key')", (key,))
            print("created vault secret 'api_key'")


if __name__ == "__main__":
    main()
