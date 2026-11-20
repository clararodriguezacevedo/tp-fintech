from collections.abc import Callable
from functools import lru_cache
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel
from supabase import Client, create_client
from supabase.lib.client_options import SyncClientOptions

from app.config import get_settings

M = TypeVar("M", bound=BaseModel)


@lru_cache
def get_db() -> Client:
    s = get_settings()
    if not s.supabase_url or not s.supabase_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set in backend/.env")
    # HTTP/1.1: over the default HTTP/2, Supabase ends the one connection every request shares after
    # a while ("Server disconnected"), and every request under way at that moment fails.
    options = SyncClientOptions(httpx_client=httpx.Client(http2=False, timeout=120))
    return create_client(s.supabase_url, s.supabase_key, options)


PAGE = 1000  # PostgREST returns at most this many rows per request


def all_rows(query: Callable[[], Any], limit: int | None = None) -> list[dict[str, Any]]:
    """Every row of a query, past PostgREST's page size. `query` builds it again for each page
    (a builder can't be reused) and must be ordered, so pages don't overlap."""
    out: list[dict[str, Any]] = []
    while limit is None or len(out) < limit:
        size = PAGE if limit is None else min(PAGE, limit - len(out))
        batch = query().range(len(out), len(out) + size - 1).execute().data
        out += batch  # type: ignore[arg-type]
        if len(batch) < size:
            break
    return out


def rows_as(model: type[M], data: object) -> list[M]:
    """Validate the rows a Supabase query returned into a row model."""
    if not isinstance(data, list):
        raise TypeError(f"expected a list of rows, got {type(data).__name__}")
    return [model.model_validate(row) for row in data]
