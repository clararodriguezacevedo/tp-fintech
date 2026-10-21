"""GDELT DOC 2.0 API, mode=artlist."""

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, field_validator


class Article(BaseModel):
    model_config = ConfigDict(extra="ignore")

    url: str
    title: str
    seendate: datetime
    domain: str = ""
    language: str = ""
    sourcecountry: str = ""

    # GDELT dates look like "20261021T153000Z".
    @field_validator("seendate", mode="before")
    @classmethod
    def _parse_seendate(cls, v):
        if isinstance(v, str) and "T" in v and "-" not in v:
            return datetime.strptime(v, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        return v


class ArtList(BaseModel):
    """GDELT returns {} when nothing matches."""

    articles: list[Article] = []
