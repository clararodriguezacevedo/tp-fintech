"""How much to trust Gemini's answers, on news already collected. Saves nothing.

  stability   the same items twice: how often the tags and directions agree
  anonymous   the same items with the company's name hidden, as Glasserman and Lin do: how often
              the direction changes. Knowing who it is can make the model overconfident.

Usage (from backend/): uv run python -m scripts.tagger_check [items]
"""

import re
import sys

from google.genai import types

from app import universe
from app.analysis import tagger
from app.analysis.tagger import TagInput, names_for, tag_items
from app.db import get_db, rows_as
from app.models.db import NewsRow

BATCH = 20
HIDDEN = "Blahblahblah"


def tags(items: list[TagInput], assets: dict[str, str]) -> dict[tuple[str, str], str]:
    out = {}
    for i in range(0, len(items), BATCH):
        for item in tag_items(items[i : i + BATCH], {}, assets):
            out |= {(item.id, t.ticker): t.direction for t in item.impacts}
    return out


def agreement(a: dict, b: dict) -> str:
    keys = set(a) | set(b)
    same_tags = len(set(a) & set(b))
    same_direction = sum(1 for k in set(a) & set(b) if a[k] == b[k])
    return f"{same_tags} of {len(keys)} tags in both runs, {same_direction} of those with the same direction"


def hide(text: str, ticker: str, name: str) -> str:
    for word in sorted(names_for(ticker, name), key=len, reverse=True):
        text = re.sub(rf"(?<![A-Za-z0-9]){re.escape(word)}(?![A-Za-z0-9])", HIDDEN, text, flags=re.IGNORECASE)
    return text


def main(n: int = 40) -> None:
    assets = universe.groups().names
    rows = rows_as(NewsRow, get_db().table("news_items").select("*").order("published_at", desc=True).limit(n).execute().data)
    items = [TagInput(id=r.id, kind="news", title=r.title, text=r.summary or "") for r in rows]
    first, second = tags(items, assets), tags(items, assets)
    print(f"{len(items)} news, {len(first)} tags")
    print("stability:", agreement(first, second))

    by_id = {i.id: i for i in items}
    changed = total = 0
    for (item_id, ticker), direction in first.items():
        item = by_id[item_id]
        name = assets.get(ticker, "")
        question = TagInput(
            id=item_id, kind="news",
            title=f"{hide(item.title, ticker, name)}", text=f"{hide(item.text, ticker, name)} (The asset {HIDDEN} is {ticker}.)",
        )
        total += 1
        batch = tag_items_unchecked([question], assets)
        if batch is not None and batch.get(ticker, direction) != direction:
            changed += 1
    print(f"anonymous: the direction changed in {changed} of {total}")


def tag_items_unchecked(items: list[TagInput], assets: dict[str, str]) -> dict[str, str] | None:
    """The answer without the checks: a hidden name can't pass the one that looks for it."""
    response = tagger._get_client().models.generate_content(
        model=tagger.get_settings().tagger_model,
        contents="\n\n".join(f"[{i.id}] {i.title}\n{i.text}" for i in items),
        config=types.GenerateContentConfig(
            system_instruction=tagger._system("news", {}, assets), temperature=0,
            response_mime_type="application/json", response_schema=tagger.TagBatch,
        ),
    )
    if not isinstance(response.parsed, tagger.TagBatch):
        return None
    return {t.ticker: t.direction for item in response.parsed.items for t in item.impacts}


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 40)
