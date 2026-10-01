"""Unusual-spend detection: robust z-score on log amounts, checked against the tail.

Spending amounts are skewed and often bimodal within a category: Food holds ₹40
teas and ₹400 dinners. On raw amounts a median/MAD rule flags every dinner. So:

1. Score each payment by its robust z-score of log(amount) within its category
   (median and MAD of the logs; 1.4826 x MAD estimates the standard deviation).
2. Also require it to be at least MIN_TAIL_RATIO times the category's 90th
   percentile, so a payment has to clear the user's own usual upper range.

The reason shown to the user names that upper range, which they can check.
Isolation Forest is kept as a comparison in ml/evaluate.py, not served here.
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from datetime import date, timedelta

from ..categories import category_names
from ..engine.calendar import local_date
from ..schemas import AnomalyItem, Txn
from .money_text import rupees

ALGORITHM = "log-mad-tail-v2"
THRESHOLD = 2.5  # robust z on log amounts (tuned on synthetic data; re-tune on real)
MIN_TAIL_RATIO = 2.0  # and at least twice the category's 90th percentile
MIN_OBSERVATIONS = 8
MIN_AMOUNT_PAISE = 30_000  # ignore anything under ₹300
SKIP_CATEGORIES = frozenset({"transfers", "income"})


def _p90(values: list[int]) -> float:
    ordered = sorted(values)
    k = 0.9 * (len(ordered) - 1)
    lo, hi = math.floor(k), math.ceil(k)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def detect_anomalies(
    txns: list[Txn],
    as_of: date,
    lookback_days: int = 120,
    recent_days: int = 30,
    exclude_merchants: frozenset[str] = frozenset(),
) -> list[AnomalyItem]:
    start = as_of - timedelta(days=lookback_days - 1)
    recent_start = as_of - timedelta(days=recent_days - 1)

    by_category: dict[str, list[Txn]] = defaultdict(list)
    for t in txns:
        day = local_date(t.ts)
        if not (start <= day <= as_of):
            continue
        if t.direction != "debit" or t.is_self_transfer or not t.category:
            continue
        if t.category in SKIP_CATEGORIES or t.category == "unknown":
            continue
        if t.merchant_norm and t.merchant_norm in exclude_merchants:
            continue
        by_category[t.category].append(t)

    names = category_names()
    flagged: list[AnomalyItem] = []
    for category, items in by_category.items():
        if len(items) < MIN_OBSERVATIONS:
            continue  # too little history to say what "usual" is
        logs = [math.log(t.amount_paise) for t in items]
        centre = statistics.median(logs)
        scale = 1.4826 * statistics.median(abs(x - centre) for x in logs)
        if scale <= 0:
            scale = statistics.pstdev(logs)
        if scale <= 0:
            continue
        amounts = [t.amount_paise for t in items]
        median = statistics.median(amounts)
        for i, t in enumerate(items):
            if local_date(t.ts) < recent_start or t.amount_paise < MIN_AMOUNT_PAISE:
                continue
            usual_max = _p90(amounts[:i] + amounts[i + 1:])  # the payment itself excluded
            score = (math.log(t.amount_paise) - centre) / scale
            tail_ratio = t.amount_paise / usual_max if usual_max > 0 else float("inf")
            if score > THRESHOLD and tail_ratio >= MIN_TAIL_RATIO:
                label = names.get(category, category.title())
                flagged.append(
                    AnomalyItem(
                        id=t.id,
                        category=category,
                        amount_paise=t.amount_paise,
                        typical_paise=int(round(median)),
                        usual_max_paise=int(round(usual_max)),
                        ratio=round(t.amount_paise / median, 2) if median > 0 else 0.0,
                        score=round(score, 2),
                        reason=(
                            f"{rupees(t.amount_paise)} is {tail_ratio:.1f}× more than 9 in 10 of "
                            f"your {label} payments (usually up to {rupees(int(usual_max))})."
                        ),
                    )
                )
    flagged.sort(key=lambda a: -a.score)
    return flagged
