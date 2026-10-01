"""Request and response shapes for /v1.

Privacy boundary: every request model forbids unknown fields, so a client that
accidentally sends an SMS body, a reference number or an account number gets a
422 instead of having that data silently accepted.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .categories import is_valid
from .engine.calendar import IST, today_ist

Direction = Literal["debit", "credit"]
Mode = Literal[
    "upi", "card", "netbanking", "atm", "imps", "neft", "rtgs", "wallet", "cash", "other"
]
Period = Literal["weekly", "28-day", "monthly", "quarterly", "yearly"]
MAX_TXNS = 5000


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _check_category(value: str | None) -> str | None:
    if value is not None and not is_valid(value):
        raise ValueError(f"unknown category '{value}'")
    return value


# ---------------------------------------------------------------- transactions


class Txn(Strict):
    """One parsed transaction, exactly as the phone is allowed to send it."""

    id: str = Field(min_length=1, max_length=64)
    ts: datetime
    amount_paise: int = Field(gt=0, le=10**12)
    direction: Direction
    merchant_norm: str = Field(default="", max_length=120)
    category: str | None = None
    account_alias: str | None = Field(default=None, max_length=64)
    mode: Mode = "other"
    is_self_transfer: bool = False
    is_refund: bool = False

    check_category = field_validator("category")(_check_category)

    @field_validator("ts")
    @classmethod
    def _to_ist(cls, value: datetime) -> datetime:
        # Naive timestamps are taken as IST; aware ones are converted to IST.
        return value.replace(tzinfo=IST) if value.tzinfo is None else value.astimezone(IST)


class Window(Strict):
    transactions: list[Txn] = Field(default_factory=list, max_length=MAX_TXNS)
    as_of: date = Field(default_factory=today_ist)


# ---------------------------------------------------------------- classify


class ClassifyItem(Strict):
    id: str = Field(min_length=1, max_length=64)
    merchant_norm: str = Field(default="", max_length=120)
    descriptor: str = Field(default="", max_length=200)
    mode: Mode = "other"
    direction: Direction = "debit"
    amount_paise: int = Field(gt=0, le=10**12)


class ClassifyRequest(Strict):
    items: list[ClassifyItem] = Field(min_length=1, max_length=500)


class Candidate(Out):
    category: str
    probability: float


class ClassifyResult(Out):
    id: str
    category: str
    confidence: float
    abstained: bool
    candidates: list[Candidate]


class ClassifyResponse(Out):
    model_version: str
    threshold: float
    items: list[ClassifyResult]


# ---------------------------------------------------------------- recurring


class RecurringItem(Out):
    merchant_norm: str
    category: str | None
    kind: Literal["subscription", "bill"]
    period: Period
    interval_days: int
    median_amount_paise: int
    occurrences: int
    first_date: date
    last_date: date
    next_due: date
    confidence: float
    monthly_cost_paise: int
    yearly_cost_paise: int
    txn_ids: list[str]


class RecurringIn(Strict):
    """A recurring item the app cached from an earlier /v1/recurring call."""

    merchant_norm: str = Field(default="", max_length=120)
    period: Period
    median_amount_paise: int = Field(gt=0, le=10**12)
    next_due: date


class RecurringResponse(Out):
    algorithm: str
    items: list[RecurringItem]


# ---------------------------------------------------------------- anomalies


class AnomalyItem(Out):
    id: str
    category: str
    amount_paise: int
    typical_paise: int  # the category's median payment
    usual_max_paise: int  # the category's 90th percentile
    ratio: float  # amount / median
    score: float
    reason: str


class AnomaliesResponse(Out):
    algorithm: str
    threshold: float
    min_observations: int
    items: list[AnomalyItem]


# ---------------------------------------------------------------- forecast


class CategorySpend(Out):
    category: str
    spent_paise: int


class ForecastRequest(Window):
    recurring: list[RecurringIn] | None = None


class ForecastResponse(Out):
    """month_end = spent_so_far + projected_variable_rest + recurring_due.

    spent_so_far includes today; projected_variable_rest is today's expected
    remainder plus variable_daily for each day after today; recurring_due is
    recurring payments still expected from today to the month's end.
    """

    month: str
    as_of: date
    days_in_month: int
    days_left: int
    spent_so_far_paise: int
    variable_daily_paise: int
    projected_variable_rest_paise: int
    recurring_due_paise: int
    projected_month_end_paise: int
    error_band_paise: int
    chosen_model: str
    backtest_mae_paise: dict[str, int | None]
    spent_by_category: list[CategorySpend]


# ---------------------------------------------------------------- safe to spend


class SafeToSpendRequest(Strict):
    as_of: date = Field(default_factory=today_ist)
    balance_paise: int = Field(ge=-(10**12), le=10**12)
    savings_target_paise: int = Field(default=0, ge=0, le=10**12)
    recurring: list[RecurringIn] | None = None
    transactions: list[Txn] | None = Field(default=None, max_length=MAX_TXNS)


class SafeToSpendResponse(Out):
    as_of: date
    days_left: int
    balance_paise: int
    recurring_due_paise: int
    savings_target_paise: int
    safe_total_paise: int
    safe_daily_paise: int
    projected_variable_paise: int | None
    projected_shortfall_paise: int | None
    status: Literal["on_track", "at_risk", "no_room"]
    formula: str


# ---------------------------------------------------------------- what-if


class CategoryChange(Strict):
    kind: Literal["category"] = "category"
    category: str
    percent_change: float = Field(ge=-100, le=200)

    check_category = field_validator("category")(_check_category)


class CancelRecurring(Strict):
    kind: Literal["cancel_recurring"]
    merchant_norm: str = Field(min_length=1, max_length=120)


class WhatIfRequest(Window):
    balance_paise: int | None = Field(default=None, ge=-(10**12), le=10**12)
    savings_target_paise: int = Field(default=0, ge=0, le=10**12)
    changes: list[CategoryChange | CancelRecurring] = Field(min_length=1, max_length=20)


class Scenario(Out):
    projected_month_end_paise: int
    variable_daily_paise: int
    projected_variable_rest_paise: int
    recurring_due_paise: int
    safe_daily_paise: int | None


class WhatIfResponse(Out):
    as_of: date
    baseline: Scenario
    scenario: Scenario
    saving_this_month_paise: int
    saving_per_month_paise: int
    notes: list[str]


# ---------------------------------------------------------------- insights bundle


class InsightsRequest(Window):
    balance_paise: int | None = Field(default=None, ge=-(10**12), le=10**12)
    savings_target_paise: int = Field(default=0, ge=0, le=10**12)


class InsightsResponse(Out):
    as_of: date
    recurring: RecurringResponse
    anomalies: AnomaliesResponse
    forecast: ForecastResponse
    safe_to_spend: SafeToSpendResponse | None


# ---------------------------------------------------------------- chat


class ChatRequest(Window):
    question: str = Field(min_length=1, max_length=500)
    balance_paise: int | None = Field(default=None, ge=-(10**12), le=10**12)
    savings_target_paise: int = Field(default=0, ge=0, le=10**12)
    provider: Literal["auto", "none", "ollama", "gemini"] = "auto"


class Fact(Out):
    label: str
    value: str


class ChatResponse(Out):
    answer: str
    intent: str | None
    facts: list[Fact]
    provider_used: str
    verified: bool
    fallback_used: bool


# ---------------------------------------------------------------- model info


class ModelInfo(Out):
    api_version: str
    classifier: dict
    algorithms: dict[str, str]
    llm: dict
