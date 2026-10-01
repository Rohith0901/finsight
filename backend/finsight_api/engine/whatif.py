"""What-if simulator: change category spending or cancel a recurring payment,
then recompute the forecast and safe-to-spend with the same engine."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta

from ..categories import UNKNOWN, category_names
from ..ml.money_text import rupees
from ..schemas import CancelRecurring, CategoryChange, RecurringItem, Scenario, Txn, WhatIfResponse
from .calendar import days_left_including, local_date
from .forecast import compute_forecast, recurring_due
from .spend import spend_delta

SHARE_WINDOW_DAYS = 60
DAYS_PER_MONTH = 30.44


def category_shares(
    txns: Sequence[Txn], as_of: date, exclude: frozenset[str]
) -> dict[str, float]:
    """Each category's share of day-to-day (non-recurring) spending, last 60 days."""
    start = as_of - timedelta(days=SHARE_WINDOW_DAYS)
    totals: dict[str, int] = {}
    for t in txns:
        if t.merchant_norm and t.merchant_norm in exclude:
            continue
        if start <= local_date(t.ts) < as_of:
            key = t.category or UNKNOWN
            totals[key] = totals.get(key, 0) + spend_delta(t)
    positive = {c: v for c, v in totals.items() if v > 0}
    grand = sum(positive.values())
    return {c: v / grand for c, v in positive.items()} if grand else {}


def compute_what_if(
    txns: Sequence[Txn],
    as_of: date,
    recurring: Sequence[RecurringItem],
    changes: Sequence[CategoryChange | CancelRecurring],
    balance_paise: int | None,
    savings_target_paise: int,
) -> WhatIfResponse:
    names = category_names()
    notes: list[str] = []
    exclude = frozenset(r.merchant_norm for r in recurring if r.merchant_norm)
    shares = category_shares(txns, as_of, exclude)

    # Scale the daily variable rate by each changed category's share of it.
    factor = 1.0
    for change in changes:
        if not isinstance(change, CategoryChange):
            continue
        share = shares.get(change.category, 0.0)
        label = names.get(change.category, change.category)
        if share == 0.0:
            notes.append(f"No recent {label} spending, so that change has no effect.")
            continue
        factor += share * change.percent_change / 100
        notes.append(
            f"{label} is {share:.0%} of your day-to-day spending, so a "
            f"{change.percent_change:+.0f}% change moves your daily rate by "
            f"{share * change.percent_change:+.1f}%."
        )
    factor = max(0.0, factor)

    cancelled = {c.merchant_norm for c in changes if isinstance(c, CancelRecurring)}
    dropped = [r for r in recurring if r.merchant_norm in cancelled]
    for name in sorted(cancelled - {r.merchant_norm for r in dropped}):
        notes.append(f"No recurring payment found for '{name}', so nothing was cancelled.")
    for r in dropped:
        notes.append(f"Cancelling {r.merchant_norm} saves {rupees(r.monthly_cost_paise)} a month.")

    baseline = compute_forecast(txns, as_of, recurring)
    # The full recurring list stays in the scenario so cancelled merchants' past
    # payments don't leak into the day-to-day rate; their remaining dues are removed.
    scaled = compute_forecast(txns, as_of, recurring, scale_v=lambda v: v * factor)
    removed = recurring_due(dropped, as_of)
    scenario_due = scaled.recurring_due_paise - removed
    scenario_total = scaled.projected_month_end_paise - removed

    d = days_left_including(as_of)

    def safe_daily(due: int) -> int | None:
        if balance_paise is None:
            return None
        return max(0, balance_paise - due - savings_target_paise) // d

    per_month = (baseline.variable_daily_paise - scaled.variable_daily_paise) * DAYS_PER_MONTH
    per_month += sum(r.monthly_cost_paise for r in dropped)

    return WhatIfResponse(
        as_of=as_of,
        baseline=Scenario(
            projected_month_end_paise=baseline.projected_month_end_paise,
            variable_daily_paise=baseline.variable_daily_paise,
            projected_variable_rest_paise=baseline.projected_variable_rest_paise,
            recurring_due_paise=baseline.recurring_due_paise,
            safe_daily_paise=safe_daily(baseline.recurring_due_paise),
        ),
        scenario=Scenario(
            projected_month_end_paise=scenario_total,
            variable_daily_paise=scaled.variable_daily_paise,
            projected_variable_rest_paise=scaled.projected_variable_rest_paise,
            recurring_due_paise=scenario_due,
            safe_daily_paise=safe_daily(scenario_due),
        ),
        saving_this_month_paise=baseline.projected_month_end_paise - scenario_total,
        saving_per_month_paise=int(round(per_month)),
        notes=notes,
    )
