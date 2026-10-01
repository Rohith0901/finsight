"""One definition of "spending", used by every calculation.

- A debit counts as spending unless it is a self transfer (own-account move or
  credit-card bill payment), because the money never left the user.
- A refund credit reduces spending on the day it arrives.
- Other credits are income or incoming transfers, never negative spending.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import date

from ..categories import UNKNOWN
from ..schemas import Txn
from .calendar import local_date


def spend_delta(t: Txn) -> int:
    if t.is_self_transfer:
        return 0
    if t.direction == "debit":
        return t.amount_paise
    if t.is_refund:
        return -t.amount_paise
    return 0


def is_income(t: Txn) -> bool:
    return t.direction == "credit" and not t.is_refund and not t.is_self_transfer


def total_spend(txns: Iterable[Txn], start: date, end: date) -> int:
    """Net spending with start <= day <= end."""
    return sum(spend_delta(t) for t in txns if start <= local_date(t.ts) <= end)


def daily_spend(
    txns: Iterable[Txn],
    start: date,
    end: date,
    exclude_merchants: frozenset[str] = frozenset(),
) -> list[int]:
    """Net spending per day from start to end inclusive (index 0 is start)."""
    n = (end - start).days + 1
    if n <= 0:
        return []
    days = [0] * n
    for t in txns:
        if t.merchant_norm and t.merchant_norm in exclude_merchants:
            continue
        d = local_date(t.ts)
        if start <= d <= end:
            days[(d - start).days] += spend_delta(t)
    return days


def spend_by_category(txns: Iterable[Txn], start: date, end: date) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for t in txns:
        if start <= local_date(t.ts) <= end:
            delta = spend_delta(t)
            if delta:
                out[t.category or UNKNOWN] += delta
    return dict(out)
