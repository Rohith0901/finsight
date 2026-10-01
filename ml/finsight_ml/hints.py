"""Descriptor hints from SMS text: the Python twin of the Dart parser's hint step."""

from __future__ import annotations

import json
import re
from functools import lru_cache

from .paths import SHARED


@lru_cache(maxsize=1)
def _patterns() -> dict[str, re.Pattern[str]]:
    data = json.loads((SHARED / "sms_hints.json").read_text(encoding="utf-8"))
    return {name: re.compile(p, re.IGNORECASE | re.ASCII) for name, p in data["hints"].items()}


def hints_from_body(body: str) -> list[str]:
    return [name for name, pattern in _patterns().items() if pattern.search(body)]


def descriptor(hints: list[str], extra: list[str] = ()) -> str:
    """Stable, sorted, space-joined hint list."""
    return " ".join(sorted(set(hints) | set(extra)))
