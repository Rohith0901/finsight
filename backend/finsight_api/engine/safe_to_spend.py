"""Safe-to-spend: plain arithmetic on verified inputs.

    safe_total = max(0, B - R - S)
    safe_daily = safe_total / d

B is the balance now (it already reflects today's spending), R the recurring
payments still expected from today to month end, S the savings target and d the
days left including today.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from ..schemas import SafeToSpendResponse, Txn
from .calendar import days_left_including
from .forecast import RecurringLike, compute_forecast, recurring_due

FORMULA = "safe_daily = max(0, balance - recurring due - savings target) / days left"


def compute_safe_to_spend(
    as_of: date,
    balance_paise: int,
    savings_target_paise: int,
    recurring: Sequence[RecurringLike],
    txns: Sequence[Txn] | None = None,
) -> SafeToSpendResponse:
    d = days_left_including(as_of)
    due = recurring_due(recurring, as_of)
    safe_total = max(0, balance_paise - due - savings_target_paise)
    safe_daily = safe_total // d

    projected: int | None = None
    shortfall: int | None = None
    if txns:
        forecast = compute_forecast(txns, as_of, recurring)
        projected = forecast.projected_variable_rest_paise
        shortfall = max(0, projected - safe_total)

    if safe_total == 0:
        status = "no_room"
    elif shortfall:
        status = "at_risk"
    else:
        status = "on_track"

    return SafeToSpendResponse(
        as_of=as_of,
        days_left=d,
        balance_paise=balance_paise,
        recurring_due_paise=due,
        savings_target_paise=savings_target_paise,
        safe_total_paise=safe_total,
        safe_daily_paise=safe_daily,
        projected_variable_paise=projected,
        projected_shortfall_paise=shortfall,
        status=status,
        formula=FORMULA,
    )
