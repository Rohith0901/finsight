"""Month-end spending forecast.

    month_end = spent_so_far + projected_variable_rest + recurring_due

- spent_so_far: all net spending from the 1st up to and including today.
- recurring_due: recurring payments still expected from today to month end.
- projected_variable_rest: max(0, V - variable spent today) + V x (days after today),
  where V is the expected daily variable (non-recurring) spend.

Three simple models estimate V. The served default is EWMA: in the rolling-origin
evaluation (ml/reports/latest.md) it beat run-rate, linear trend and per-user
automatic selection. Run-rate is the fallback with under a week of history. The
backtest on the user's own previous months still runs, to size the error band.
"""

from __future__ import annotations

import statistics
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Protocol

import numpy as np

from ..ml.recurring import due_dates, grace_for
from ..schemas import CategorySpend, ForecastResponse, Txn
from .calendar import (
    add_months,
    days_in_month,
    days_left_including,
    local_date,
    month_end,
    month_key,
    month_start,
    previous_month,
)
from .spend import daily_spend, spend_by_category, total_spend

MODELS = ("run_rate", "ewma", "linear")
WARM_UP_DAYS = 7  # early in a month, run-rate leans on last month's rate
EWMA_HALF_LIFE = 14
HISTORY_DAYS = 60
LINEAR_MIN_DAYS = 21
BACKTEST_MONTHS = 3
BACKTEST_CUTOFF_DAYS = (8, 15, 22)
NO_BACKTEST_BAND = 0.25  # +/-25% when there is no history to measure error on


class RecurringLike(Protocol):
    merchant_norm: str
    period: str
    median_amount_paise: int
    next_due: date


@dataclass(frozen=True)
class Context:
    txns: Sequence[Txn]
    exclude: frozenset[str]  # merchants whose payments are counted in recurring_due
    data_start: date


def _series(ctx: Context, start: date, end: date) -> list[int]:
    return daily_spend(ctx.txns, max(start, ctx.data_start), end, ctx.exclude)


def v_run_rate(ctx: Context, cutoff: date) -> float:
    """Average daily variable spend this month before cutoff."""
    ms = month_start(cutoff)
    elapsed = (cutoff - ms).days
    mtd = sum(daily_spend(ctx.txns, ms, cutoff - timedelta(days=1), ctx.exclude)) if elapsed else 0
    prev_start = previous_month(cutoff)
    has_prev = ctx.data_start <= prev_start
    prev_rate = 0.0
    if has_prev:
        prev_end = ms - timedelta(days=1)
        prev_days = (prev_end - prev_start).days + 1
        prev_rate = sum(daily_spend(ctx.txns, prev_start, prev_end, ctx.exclude)) / prev_days
    if elapsed >= WARM_UP_DAYS or not has_prev:
        if elapsed:
            return mtd / elapsed
        return prev_rate if has_prev else 0.0
    return (mtd + prev_rate * (WARM_UP_DAYS - elapsed)) / WARM_UP_DAYS


def v_ewma(ctx: Context, cutoff: date) -> float | None:
    """Exponentially weighted daily average over the last 60 days."""
    start = cutoff - timedelta(days=HISTORY_DAYS)
    series = _series(ctx, start, cutoff - timedelta(days=1))
    if len(series) < WARM_UP_DAYS:
        return None
    n = len(series)
    weights = [0.5 ** ((n - 1 - i) / EWMA_HALF_LIFE) for i in range(n)]
    return sum(w * x for w, x in zip(weights, series)) / sum(weights)


def v_linear(ctx: Context, cutoff: date, days_ahead: int) -> float | None:
    """Least-squares trend over the last 60 days, averaged over the days ahead."""
    start = cutoff - timedelta(days=HISTORY_DAYS)
    series = _series(ctx, start, cutoff - timedelta(days=1))
    if len(series) < LINEAR_MIN_DAYS:
        return None
    t = np.arange(len(series), dtype=float)
    slope, intercept = np.polyfit(t, np.asarray(series, dtype=float), 1)
    mid = len(series) + (max(days_ahead, 1) - 1) / 2
    return max(0.0, float(intercept + slope * mid))


def estimate_v(model: str, ctx: Context, cutoff: date, days_ahead: int) -> float | None:
    if model == "run_rate":
        return v_run_rate(ctx, cutoff)
    if model == "ewma":
        return v_ewma(ctx, cutoff)
    if model == "linear":
        return v_linear(ctx, cutoff, days_ahead)
    raise ValueError(model)


def backtest(ctx: Context, as_of: date) -> tuple[dict[str, float | None], float | None]:
    """MAE of each model's rest-of-month projection on up to 3 previous months."""
    errors: dict[str, list[float]] = {m: [] for m in MODELS}
    rest_lengths: list[int] = []
    for k in range(1, BACKTEST_MONTHS + 1):
        m_start = add_months(month_start(as_of), -k)
        if m_start < ctx.data_start:
            break
        m_end = month_end(m_start)
        for day in BACKTEST_CUTOFF_DAYS:
            cutoff = m_start.replace(day=day)
            rest = (m_end - cutoff).days + 1
            actual = sum(daily_spend(ctx.txns, cutoff, m_end, ctx.exclude))
            rest_lengths.append(rest)
            for model in MODELS:
                v = estimate_v(model, ctx, cutoff, rest)
                if v is not None:
                    errors[model].append(abs(v * rest - actual))
    mae = {m: (statistics.fmean(e) if e else None) for m, e in errors.items()}
    return mae, (statistics.fmean(rest_lengths) if rest_lengths else None)


DEFAULT_MODEL = "ewma"


def choose_model(mae: dict[str, float | None]) -> str:
    """Per-user selection by backtest error (evaluated as "auto"; not the default)."""
    scored = [(v, MODELS.index(m), m) for m, v in mae.items() if v is not None]
    return min(scored)[2] if scored else "run_rate"


def recurring_due(items: Iterable[RecurringLike], as_of: date) -> int:
    end = month_end(as_of)
    total = 0
    for item in items:
        dates = due_dates(item.next_due, item.period, as_of, end, grace_for(item.period))
        total += item.median_amount_paise * len(dates)
    return total


def build_context(txns: Sequence[Txn], as_of: date, recurring: Iterable[RecurringLike]) -> Context:
    exclude = frozenset(r.merchant_norm for r in recurring if r.merchant_norm)
    dates = [local_date(t.ts) for t in txns]
    return Context(txns=txns, exclude=exclude, data_start=min(dates) if dates else as_of)


def variable_rest(ctx: Context, as_of: date, v: float) -> int:
    today_variable = sum(daily_spend(ctx.txns, as_of, as_of, ctx.exclude))
    after_today = days_left_including(as_of) - 1
    return int(round(max(0.0, v - today_variable) + v * after_today))


def compute_forecast(
    txns: Sequence[Txn],
    as_of: date,
    recurring: Sequence[RecurringLike],
    scale_v: Callable[[float], float] | None = None,
    model: str | None = None,
) -> ForecastResponse:
    """model: "ewma" (default), "run_rate", "linear" or "auto" (backtest picks)."""
    ctx = build_context(txns, as_of, recurring)
    d = days_left_including(as_of)
    mae, mean_rest = backtest(ctx, as_of)
    wanted = model or DEFAULT_MODEL
    chosen = choose_model(mae) if wanted == "auto" else wanted
    v = estimate_v(chosen, ctx, as_of, d)
    if v is None:  # under a week of history: fall back to run-rate, which always works
        chosen, v = "run_rate", v_run_rate(ctx, as_of)
    if scale_v is not None:
        v = scale_v(v)
    rest = variable_rest(ctx, as_of, v)
    due = recurring_due(recurring, as_of)
    ms = month_start(as_of)
    spent = total_spend(txns, ms, as_of)
    if mae.get(chosen) is not None and mean_rest:
        band = mae[chosen] * d / mean_rest
    else:
        band = NO_BACKTEST_BAND * rest
    by_cat = spend_by_category(txns, ms, as_of)
    return ForecastResponse(
        month=month_key(as_of),
        as_of=as_of,
        days_in_month=days_in_month(as_of),
        days_left=d,
        spent_so_far_paise=spent,
        variable_daily_paise=int(round(v)),
        projected_variable_rest_paise=rest,
        recurring_due_paise=due,
        projected_month_end_paise=spent + rest + due,
        error_band_paise=int(round(band)),
        chosen_model=chosen,
        backtest_mae_paise={m: (int(round(x)) if x is not None else None) for m, x in mae.items()},
        spent_by_category=[
            CategorySpend(category=c, spent_paise=p)
            for c, p in sorted(by_cat.items(), key=lambda kv: -kv[1])
        ],
    )
