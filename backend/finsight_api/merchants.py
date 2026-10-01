"""Display names for merchant keys (shared/merchants.json)."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

_DEFAULT_SHARED = Path(__file__).resolve().parents[2] / "shared"


@lru_cache(maxsize=1)
def _names() -> dict[str, str]:
    root = os.environ.get("FINSIGHT_SHARED_DIR")
    path = (Path(root) if root else _DEFAULT_SHARED) / "merchants.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return {m["id"]: m["name"] for m in data["merchants"]}


def display_name(merchant_norm: str) -> str:
    if not merchant_norm:
        return "an unknown merchant"
    if merchant_norm.startswith("person:"):
        return "a person"
    known = _names().get(merchant_norm)
    if known:
        return known
    return " ".join(w.capitalize() for w in merchant_norm.replace("_", " ").split())
