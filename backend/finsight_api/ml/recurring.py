"""Recurring-payment detection by interval and amount regularity.

For each merchant, the detector tries the whole payment series first (bills whose
amount varies, such as electricity), then each cluster of near-identical amounts
(subscriptions hidden among ordinary orders, such as a ₹299 membership among many
food orders). A series is recurring when at least 75% of its gaps match one period
and at least 75% of its amounts sit close to the median.
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from ..engine.calendar import add_months, local_date
from ..schemas import RecurringItem, Txn

ALGORITHM = "interval-amount-v1"


@dataclass(frozen=True)
class PeriodSpec:
    name: str
    nominal_days: float
    tolerance_days: float
    min_occurrences: int


# Three payments is the least evidence of a rhythm: two payments 91 days apart at a
# shop you visit every week is a coincidence, not a quarterly plan. Longer periods
# therefore need a longer window of history before they can be detected.
PERIODS = (
    PeriodSpec("weekly", 7, 1.5, 5),
    PeriodSpec("28-day", 28, 2, 3),
    PeriodSpec("monthly", 30.44, 3.5, 3),
    PeriodSpec("quarterly", 91.3, 8, 3),
    PeriodSpec("yearly", 365.25, 12, 3),
)
CLUSTER_AMOUNT = 0.05  # a series found inside a busy merchant must repeat almost exactly
_BY_NAME = {p.name: p for p in PERIODS}

REGULAR_SHARE = 0.75  # share of gaps / amounts that must be regular
STABLE_AMOUNT = 0.10  # subscription: within 10% of the median
BILL_AMOUNT = 0.50  # bill: within 50% of the median


def next_due_after(last: date, period: str, anchor_day: int | None = None) -> date:
    if period == "monthly":
        return add_months(last, 1, anchor_day)
    if period == "quarterly":
        return add_months(last, 3, anchor_day)
    if period == "yearly":
        return add_months(last, 12, anchor_day)
    return last + timedelta(days=round(_BY_NAME[period].nominal_days))


def due_dates(next_due: date, period: str, start: date, end: date, grace_days: int) -> list[date]:
    """Expected payment dates within [start, end].

    A due date up to grace_days before start still counts once: the payment is late
    rather than cancelled. Anything older is treated as stopped.
    """
    out: list[date] = []
    d = next_due
    anchor = next_due.day
    if d < start - timedelta(days=grace_days):
        return out
    if d < start:
        out.append(start)
        d = next_due_after(d, period, anchor)
    while d <= end:
        if d >= start:
            out.append(d)
        d = next_due_after(d, period, anchor)
    return out


def grace_for(period: str) -> int:
    return max(2, int(_BY_NAME[period].tolerance_days) + 1)


def _share_within(values: list[float], centre: float, tolerance: float) -> float:
    if not values:
        return 0.0
    return sum(1 for v in values if abs(v - centre) <= tolerance) / len(values)


def _amount_share(amounts: list[int], median: float, rel: float) -> float:
    # A small absolute floor (₹10) so tiny subscriptions with tax rounding still match.
    tol = max(rel * median, 1000)
    return _share_within([float(a) for a in amounts], median, tol)


def _best_period(days: list[date]) -> tuple[PeriodSpec, float] | None:
    gaps = [(b - a).days for a, b in zip(days, days[1:])]
    if not gaps:
        return None
    median_gap = statistics.median(gaps)
    best: tuple[PeriodSpec, float, float] | None = None
    for spec in PERIODS:
        if len(days) < spec.min_occurrences:
            continue
        share = _share_within([float(g) for g in gaps], spec.nominal_days, spec.tolerance_days)
        if share < REGULAR_SHARE:
            continue
        closeness = abs(median_gap - spec.nominal_days)
        if best is None or closeness < best[2]:
            best = (spec, share, closeness)
    return (best[0], best[1]) if best else None


def _one_per_day(txns: list[Txn]) -> list[Txn]:
    """Keep the first payment per day so same-day repeats don't break the rhythm."""
    seen: set[date] = set()
    out: list[Txn] = []
    for t in sorted(txns, key=lambda t: t.ts):
        d = local_date(t.ts)
        if d not in seen:
            seen.add(d)
            out.append(t)
    return out


def _amount_clusters(txns: list[Txn]) -> list[list[Txn]]:
    """Group payments whose amounts are within 10% of the cluster's first amount."""
    clusters: list[list[Txn]] = []
    for t in sorted(txns, key=lambda t: t.amount_paise):
        if clusters:
            head = clusters[-1][0].amount_paise
            if t.amount_paise <= head * (1 + STABLE_AMOUNT) + 1000:
                clusters[-1].append(t)
                continue
        clusters.append([t])
    return clusters


def _evaluate(series: list[Txn], as_of: date, cluster: bool = False) -> RecurringItem | None:
    series = _one_per_day(series)
    days = [local_date(t.ts) for t in series]
    found = _best_period(days)
    if found is None:
        return None
    spec, gap_share = found
    # Stale series (no payment for 1.6 periods) are treated as cancelled.
    if (as_of - days[-1]).days > spec.nominal_days * 1.6 + spec.tolerance_days:
        return None
    amounts = [t.amount_paise for t in series]
    median = statistics.median(amounts)
    stable = _amount_share(amounts, median, CLUSTER_AMOUNT if cluster else STABLE_AMOUNT)
    if stable >= REGULAR_SHARE:
        kind, amount_share = "subscription", stable
    elif cluster or spec.name == "weekly":
        return None  # variable-amount "bills" only make sense for a merchant's whole series
    else:
        loose = _amount_share(amounts, median, BILL_AMOUNT)
        if loose < REGULAR_SHARE:
            return None
        kind, amount_share = "bill", loose
    occ_factor = min(1.0, 0.6 + 0.1 * len(series))
    confidence = round(gap_share * amount_share * occ_factor, 3)
    anchor = round(statistics.median(d.day for d in days)) if spec.name in (
        "monthly", "quarterly", "yearly") else None
    next_due = next_due_after(days[-1], spec.name, anchor)
    categories = Counter(t.category for t in series if t.category)
    median_int = int(round(median))
    return RecurringItem(
        merchant_norm=series[0].merchant_norm,
        category=categories.most_common(1)[0][0] if categories else None,
        kind=kind,
        period=spec.name,  # type: ignore[arg-type]
        interval_days=int(round(spec.nominal_days)),
        median_amount_paise=median_int,
        occurrences=len(series),
        first_date=days[0],
        last_date=days[-1],
        next_due=next_due,
        confidence=confidence,
        monthly_cost_paise=int(round(median * 30.44 / spec.nominal_days)),
        yearly_cost_paise=int(round(median * 365.25 / spec.nominal_days)),
        txn_ids=[t.id for t in series],
    )


def detect_recurring(txns: list[Txn], as_of: date) -> list[RecurringItem]:
    groups: dict[str, list[Txn]] = defaultdict(list)
    for t in txns:
        if (
            t.direction == "debit"
            and not t.is_self_transfer
            and t.merchant_norm
            and local_date(t.ts) <= as_of
        ):
            groups[t.merchant_norm].append(t)

    items: list[RecurringItem] = []
    for series in groups.values():
        whole = _evaluate(series, as_of)
        if whole is not None:
            items.append(whole)
            continue
        for cluster in _amount_clusters(series):
            if len(cluster) >= 3:
                found = _evaluate(cluster, as_of, cluster=True)
                if found is not None:
                    items.append(found)
    items.sort(key=lambda i: (-i.monthly_cost_paise, i.merchant_norm))
    return items
