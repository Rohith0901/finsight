"""Everything the assistant may say comes from here.

FinanceContext computes each figure once per request. Tools expose those
figures to a model as JSON with amounts in whole rupees. Each tool is marked
"aggregate" (totals, rates, category shares) or "detail" (merchant names,
single transactions); cloud providers are only ever offered aggregate tools.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from functools import cached_property
from typing import Any

from ..categories import category_names
from ..engine.calendar import add_months, days_in_month, local_date, month_start
from ..engine.forecast import compute_forecast
from ..engine.safe_to_spend import compute_safe_to_spend
from ..engine.spend import spend_by_category, spend_delta
from ..merchants import display_name
from ..ml.anomaly import detect_anomalies
from ..ml.recurring import detect_recurring
from ..schemas import AnomalyItem, ForecastResponse, RecurringItem, SafeToSpendResponse, Txn


def rs(paise: int | float) -> int:
    """Whole rupees, rounding half up."""
    return int((abs(paise) + 50) // 100) * (1 if paise >= 0 else -1)


class FinanceContext:
    def __init__(self, txns: list[Txn], as_of: date, balance_paise: int | None,
                 savings_target_paise: int):
        self.txns = txns
        self.as_of = as_of
        self.balance_paise = balance_paise
        self.savings_target_paise = savings_target_paise
        self.names = category_names()

    @cached_property
    def recurring(self) -> list[RecurringItem]:
        return detect_recurring(self.txns, self.as_of)

    @cached_property
    def forecast(self) -> ForecastResponse:
        return compute_forecast(self.txns, self.as_of, self.recurring)

    @cached_property
    def anomalies(self) -> list[AnomalyItem]:
        exclude = frozenset(r.merchant_norm for r in self.recurring)
        return detect_anomalies(self.txns, self.as_of, exclude_merchants=exclude)

    @cached_property
    def safe(self) -> SafeToSpendResponse | None:
        if self.balance_paise is None:
            return None
        return compute_safe_to_spend(
            self.as_of, self.balance_paise, self.savings_target_paise, self.recurring, self.txns
        )

    def label(self, category: str) -> str:
        return self.names.get(category, category.title())

    def txn(self, txn_id: str) -> Txn | None:
        return next((t for t in self.txns if t.id == txn_id), None)

    # ------------------------------------------------------------ periods

    def period(self, name: str) -> tuple[date, date]:
        if name == "last_month":
            start = add_months(month_start(self.as_of), -1)
            return start, start.replace(day=days_in_month(start))
        if name == "last_30_days":
            return self.as_of - timedelta(days=29), self.as_of
        return month_start(self.as_of), self.as_of

    def same_period_last_month(self) -> tuple[date, date]:
        start = add_months(month_start(self.as_of), -1)
        return start, start.replace(day=min(self.as_of.day, days_in_month(start)))


# ---------------------------------------------------------------- tools


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    privacy: str  # "aggregate" | "detail"
    run: Callable[[FinanceContext, dict[str, Any]], dict[str, Any]]


def _month_summary(ctx: FinanceContext, _: dict) -> dict:
    f = ctx.forecast
    top = f.spent_by_category[:5]
    return {
        "month": f.month,
        "as_of": f.as_of.isoformat(),
        "days_left": f.days_left,
        "spent_so_far_rupees": rs(f.spent_so_far_paise),
        "projected_month_end_rupees": rs(f.projected_month_end_paise),
        "give_or_take_rupees": rs(f.error_band_paise),
        "daily_rate_rupees": rs(f.variable_daily_paise),
        "upcoming_recurring_rupees": rs(f.recurring_due_paise),
        "top_categories": [
            {"category": ctx.label(c.category), "spent_rupees": rs(c.spent_paise)} for c in top
        ],
    }


def _spend_by_category(ctx: FinanceContext, args: dict) -> dict:
    period = args.get("period", "this_month")
    if period not in ("this_month", "last_month", "last_30_days"):
        period = "this_month"
    start, end = ctx.period(period)
    by_cat = spend_by_category(ctx.txns, start, end)
    total = sum(v for v in by_cat.values() if v > 0)
    rows = sorted(((c, v) for c, v in by_cat.items() if v > 0), key=lambda kv: -kv[1])
    return {
        "period": period,
        "from": start.isoformat(),
        "to": end.isoformat(),
        "total_rupees": rs(total),
        "categories": [
            {
                "category": ctx.label(c),
                "spent_rupees": rs(v),
                "share_percent": round(100 * v / total, 1) if total else 0.0,
            }
            for c, v in rows
        ],
    }


def _compare_with_last_month(ctx: FinanceContext, _: dict) -> dict:
    this_start, this_end = ctx.period("this_month")
    last_start, last_end = ctx.same_period_last_month()
    now = spend_by_category(ctx.txns, this_start, this_end)
    before = spend_by_category(ctx.txns, last_start, last_end)
    total_now = sum(now.values())
    total_before = sum(before.values())
    cats = sorted(set(now) | set(before), key=lambda c: -abs(now.get(c, 0) - before.get(c, 0)))
    return {
        "this_month_to_date_rupees": rs(total_now),
        "last_month_same_days_rupees": rs(total_before),
        "difference_rupees": rs(total_now - total_before),
        "change_percent": round(100 * (total_now - total_before) / total_before, 1)
        if total_before > 0 else None,
        "same_days": f"1-{this_end.day}",
        "categories": [
            {
                "category": ctx.label(c),
                "this_month_rupees": rs(now.get(c, 0)),
                "last_month_rupees": rs(before.get(c, 0)),
                "difference_rupees": rs(now.get(c, 0) - before.get(c, 0)),
            }
            for c in cats[:6]
        ],
    }


def _safe_to_spend(ctx: FinanceContext, _: dict) -> dict:
    s = ctx.safe
    if s is None:
        return {"available": False, "reason": "no balance known"}
    return {
        "available": True,
        "balance_rupees": rs(s.balance_paise),
        "upcoming_recurring_rupees": rs(s.recurring_due_paise),
        "savings_target_rupees": rs(s.savings_target_paise),
        "safe_total_rupees": rs(s.safe_total_paise),
        "safe_daily_rupees": rs(s.safe_daily_paise),
        "days_left": s.days_left,
        "status": s.status,
        "projected_day_to_day_rupees": rs(s.projected_variable_paise or 0),
        "shortfall_rupees": rs(s.projected_shortfall_paise or 0),
    }


def _check_affordability(ctx: FinanceContext, args: dict) -> dict:
    try:
        amount = float(args.get("amount_rupees", 0))
    except (TypeError, ValueError):
        amount = 0.0
    s = ctx.safe
    if s is None or amount <= 0:
        return {"available": False, "reason": "no balance known" if s is None else "no amount"}
    paise = int(round(amount * 100))
    if paise <= s.safe_daily_paise:
        verdict = "within_today"
    elif paise <= s.safe_total_paise:
        verdict = "within_month"
    else:
        verdict = "not_affordable"
    after_total = max(0, s.safe_total_paise - paise)
    return {
        "available": True,
        "amount_rupees": rs(paise),
        "verdict": verdict,
        "safe_total_rupees": rs(s.safe_total_paise),
        "safe_daily_rupees": rs(s.safe_daily_paise),
        "safe_daily_after_rupees": rs(after_total // s.days_left),
        "days_left": s.days_left,
        "short_by_rupees": rs(max(0, paise - s.safe_total_paise)),
    }


def _list_recurring(ctx: FinanceContext, _: dict) -> dict:
    items = ctx.recurring
    return {
        "count": len(items),
        "monthly_total_rupees": rs(sum(i.monthly_cost_paise for i in items)),
        "items": [
            {
                "merchant": display_name(i.merchant_norm),
                "period": i.period,
                "amount_rupees": rs(i.median_amount_paise),
                "next_due": i.next_due.isoformat(),
                "monthly_cost_rupees": rs(i.monthly_cost_paise),
            }
            for i in sorted(items, key=lambda i: i.next_due)
        ],
    }


def _unusual_payments(ctx: FinanceContext, _: dict) -> dict:
    out = []
    for a in ctx.anomalies[:5]:
        t = ctx.txn(a.id)
        out.append(
            {
                "date": local_date(t.ts).isoformat() if t else None,
                "merchant": display_name(t.merchant_norm) if t else None,
                "category": ctx.label(a.category),
                "amount_rupees": rs(a.amount_paise),
                "usually_up_to_rupees": rs(a.usual_max_paise),
            }
        )
    return {"count": len(ctx.anomalies), "window_days": 30, "items": out}


def _merchant_spend(ctx: FinanceContext, args: dict) -> dict:
    query = str(args.get("merchant", "")).strip().lower()
    period = args.get("period", "this_month")
    start, end = ctx.period(period if period in ("this_month", "last_month", "last_30_days")
                            else "this_month")
    matched = [
        t for t in ctx.txns
        if query and (query in t.merchant_norm.lower()
                      or query in display_name(t.merchant_norm).lower())
        and start <= local_date(t.ts) <= end
    ]
    total = sum(spend_delta(t) for t in matched)
    return {"merchant": query, "period": period, "total_rupees": rs(total), "count": len(matched)}


_PERIOD_PARAM = {
    "type": "string",
    "enum": ["this_month", "last_month", "last_30_days"],
    "description": "Which period to total.",
}
_NO_PARAMS: dict[str, Any] = {"type": "object", "properties": {}}

TOOLS: tuple[Tool, ...] = (
    Tool("month_summary", "This month so far: spending, projection to month end, daily rate, "
         "upcoming recurring payments and top categories.", _NO_PARAMS, "aggregate",
         _month_summary),
    Tool("spend_by_category", "Spending per category for a period, with each category's share.",
         {"type": "object", "properties": {"period": _PERIOD_PARAM}}, "aggregate",
         _spend_by_category),
    Tool("compare_with_last_month", "This month so far against the same days of last month, "
         "overall and per category.", _NO_PARAMS, "aggregate", _compare_with_last_month),
    Tool("safe_to_spend", "How much can be spent safely per day and in total until month end, "
         "after upcoming recurring payments and the savings target.", _NO_PARAMS, "aggregate",
         _safe_to_spend),
    Tool("check_affordability", "Whether a purchase of a given amount fits the safe-to-spend "
         "budget.", {"type": "object", "properties": {"amount_rupees": {
             "type": "number", "description": "Purchase amount in rupees."}},
             "required": ["amount_rupees"]}, "aggregate", _check_affordability),
    Tool("list_recurring", "Detected subscriptions and regular bills with amounts and next due "
         "dates.", _NO_PARAMS, "detail", _list_recurring),
    Tool("unusual_payments", "Unusually large payments in the last 30 days.", _NO_PARAMS,
         "detail", _unusual_payments),
    Tool("merchant_spend", "Total spent at one merchant in a period.", {
        "type": "object", "properties": {
            "merchant": {"type": "string", "description": "Merchant name, e.g. Swiggy."},
            "period": _PERIOD_PARAM}, "required": ["merchant"]}, "detail", _merchant_spend),
)
TOOLS_BY_NAME = {t.name: t for t in TOOLS}


def tools_for(cloud: bool) -> list[Tool]:
    return [t for t in TOOLS if not cloud or t.privacy == "aggregate"]
