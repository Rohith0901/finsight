"""Category list shared with the app (shared/categories.json)."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

_DEFAULT_SHARED = Path(__file__).resolve().parents[2] / "shared"
UNKNOWN = "unknown"


def _shared_dir() -> Path:
    value = os.environ.get("FINSIGHT_SHARED_DIR")
    return Path(value).expanduser().resolve() if value else _DEFAULT_SHARED


@lru_cache(maxsize=1)
def category_ids() -> tuple[str, ...]:
    data = json.loads((_shared_dir() / "categories.json").read_text(encoding="utf-8"))
    return tuple(c["id"] for c in data["categories"])


@lru_cache(maxsize=1)
def category_names() -> dict[str, str]:
    data = json.loads((_shared_dir() / "categories.json").read_text(encoding="utf-8"))
    names = {c["id"]: c["name"] for c in data["categories"]}
    names[UNKNOWN] = "Uncategorised"
    return names


def is_valid(category: str) -> bool:
    return category == UNKNOWN or category in category_ids()


# Categories that are not discretionary spending. Transfers and income never count
# towards "variable spend"; the forecast treats them separately.
NON_SPEND = frozenset({"income"})
