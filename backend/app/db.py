from functools import lru_cache
from typing import TypeVar

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


def rows_as(model: type[M], data: object) -> list[M]:
    """Validate the rows a Supabase query returned into a row model."""
    if not isinstance(data, list):
        raise TypeError(f"expected a list of rows, got {type(data).__name__}")
    return [model.model_validate(row) for row in data]
