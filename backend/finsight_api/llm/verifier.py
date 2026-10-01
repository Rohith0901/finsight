"""Every number in an answer must come from a tool result or the question.

An answer that mentions a number the tools never produced is rejected, and the
assistant falls back to a templated answer built from the tool results.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_NUMBER = re.compile(
    r"(?<![\w.])(?:₹|rs\.?\s?|inr\s?)?"
    r"(\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"\s*(%|k\b|lakhs?\b|crores?\b)?",
    re.IGNORECASE,
)
_MULTIPLIER = {"k": 1_000, "lakh": 100_000, "lakhs": 100_000, "crore": 10_000_000,
               "crores": 10_000_000}
FREE_SMALL_INTEGERS = frozenset({0, 1, 2, 3})


@dataclass(frozen=True)
class Found:
    text: str
    value: float
    percent: bool


def extract(text: str) -> list[Found]:
    out = []
    for m in _NUMBER.finditer(text):
        raw, unit = m.group(1), (m.group(2) or "").lower()
        value = float(raw.replace(",", ""))
        if unit in _MULTIPLIER:
            value *= _MULTIPLIER[unit]
        out.append(Found(m.group(0).strip(), value, unit == "%"))
    return out


def collect(source: Any, into: set[float] | None = None) -> set[float]:
    """All numbers inside a JSON-like value, including those embedded in strings."""
    into = set() if into is None else into
    if isinstance(source, bool) or source is None:
        return into
    if isinstance(source, (int, float)):
        into.add(float(source))
    elif isinstance(source, str):
        for f in extract(source):
            into.add(f.value)
        for part in re.findall(r"\d+", source):  # dates such as 2026-09-12 → 2026, 9, 12
            into.add(float(part))
    elif isinstance(source, dict):
        for v in source.values():
            collect(v, into)
    elif isinstance(source, (list, tuple)):
        into.add(float(len(source)))
        for v in source:
            collect(v, into)
    return into


def _close(value: float, allowed: float, percent: bool) -> bool:
    if percent:
        return abs(value - allowed) <= 0.51
    if abs(value - allowed) <= max(0.51, 0.005 * abs(allowed)):
        return True
    # "about ₹12,000" for 12,345: rounding to hundreds or thousands is fine.
    return abs(allowed) >= 1000 and value in (round(allowed, -2), round(allowed, -3))


@dataclass(frozen=True)
class Verdict:
    ok: bool
    unsupported: list[str]


def verify(answer: str, allowed: set[float]) -> Verdict:
    bad = []
    for f in extract(answer):
        if not f.percent and f.value.is_integer() and int(f.value) in FREE_SMALL_INTEGERS:
            continue
        if not any(_close(f.value, a, f.percent) for a in allowed):
            bad.append(f.text)
    return Verdict(ok=not bad, unsupported=bad)
