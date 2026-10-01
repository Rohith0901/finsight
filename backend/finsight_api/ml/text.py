"""Feature text for the category classifier.

Training (ml/) and serving (this package) both call these functions, so the
text a model is trained on is exactly the text it sees in production.
"""

from __future__ import annotations

import re

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
AMOUNT_EDGES_RUPEES = (50, 200, 500, 1000, 2500, 5000, 10000, 50000)


def normalize(text: str) -> str:
    return _NON_ALNUM.sub(" ", (text or "").lower()).strip()


def amount_bucket(amount_paise: int) -> str:
    rupees = amount_paise / 100
    for edge in AMOUNT_EDGES_RUPEES:
        if rupees < edge:
            return f"lt{edge}"
    return f"ge{AMOUNT_EDGES_RUPEES[-1]}"


def word_text(
    merchant_norm: str, descriptor: str, mode: str, direction: str, amount_paise: int
) -> str:
    """Words: merchant tokens, channel hints and coarse context tokens."""
    parts = [
        normalize(merchant_norm),
        normalize(descriptor),
        f"mode_{mode}",
        f"dir_{direction}",
        f"amt_{amount_bucket(amount_paise)}",
    ]
    return " ".join(p for p in parts if p)


def char_text(merchant_norm: str) -> str:
    """Characters of the merchant name only: this is what generalises to unseen shops."""
    return normalize(merchant_norm)
