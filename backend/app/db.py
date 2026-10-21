from functools import lru_cache
from typing import TypeVar

from pydantic import BaseModel
from supabase import Client, create_client

from app.config import get_settings

M = TypeVar("M", bound=BaseModel)


@lru_cache
def get_db() -> Client:
    s = get_settings()
    if not s.supabase_url or not s.supabase_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set in backend/.env")
    return create_client(s.supabase_url, s.supabase_key)


def rows_as(model: type[M], data: object) -> list[M]:
    """Validate the rows a Supabase query returned into a row model."""
    if not isinstance(data, list):
        raise TypeError(f"expected a list of rows, got {type(data).__name__}")
    return [model.model_validate(row) for row in data]
