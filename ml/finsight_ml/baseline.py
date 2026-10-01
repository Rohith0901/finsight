"""The baseline every model must beat: merchant lookup plus keyword rules.

It abstains (returns None) when nothing matches, which counts as wrong in
accuracy and F1, and is reported separately as coverage.
"""

from __future__ import annotations

from finsight_api.ml.text import normalize

from .names import rules

KEYWORDS = {
    "food": "sweets bakery bakers cafe restaurant hotel dhaba canteen mess tea coffee juice "
            "biryani tiffin idli chaat momos pizza food foods kitchen bhojanalaya bhandar court",
    "groceries": "kirana provision provisions general supermarket mart dairy milk vegetables "
                 "fruits fresh grocery needs departmental",
    "transport": "fuel petrol travels auto parking tyres motors rentals cab cabs taxi metro",
    "shopping": "garments textiles footwear electronics mobiles fashion collections stationery "
                "book books depot gift opticals handloom decor hardware",
    "health": "medical medicals pharmacy chemist clinic hospital diagnostics dental eye care "
              "physiotherapy",
    "entertainment": "cinemas cinema multiplex gaming bowling amusement club arena turf",
    "other": "academy coaching institute insurance xerox tailors laundry salon parlour beauty",
}
_WORDS = {c: frozenset(w.split()) for c, w in KEYWORDS.items()}
INCOME_HINTS = frozenset({"salary", "interest", "cashback"})


def _lookup() -> dict[str, str]:
    return {m["id"]: m["category"] for m in rules()["merchants"]}


def predict(merchant_norm: str, descriptor: str, direction: str) -> str | None:
    table = _lookup()
    if merchant_norm in table:
        return table[merchant_norm]
    hints = set(descriptor.split())
    if direction == "credit" and hints & INCOME_HINTS:
        return "income"
    tokens = set(normalize(merchant_norm).split())
    scores = {c: len(tokens & words) for c, words in _WORDS.items()}
    best = max(scores, key=lambda c: scores[c])
    return best if scores[best] > 0 else None
