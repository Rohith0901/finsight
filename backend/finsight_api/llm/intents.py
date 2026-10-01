"""Deterministic answers for the questions people ask most.

Small local models call tools unreliably, so these intents are matched by
pattern and answered from tool results with a template. A model may then only
rephrase the template, and the verifier checks it kept the numbers.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from ..ml.money_text import group_indian
from ..schemas import Fact
from .context import TOOLS_BY_NAME, FinanceContext

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def inr(rupees: int) -> str:
    return ("-₹" if rupees < 0 else "₹") + group_indian(abs(rupees))


def day_month(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.day} {MONTHS[d.month - 1]}"


@dataclass
class IntentAnswer:
    intent: str
    text: str
    facts: list[Fact]
    sensitive: bool  # True if the answer names merchants or single transactions
    data: dict[str, Any] = field(default_factory=dict)  # tool outputs used


def _run(ctx: FinanceContext, name: str, **args: Any) -> dict[str, Any]:
    return TOOLS_BY_NAME[name].run(ctx, args)


_NO_BALANCE = (
    "I need your current balance for that. The app picks it up from bank SMS that show "
    "an available balance, or you can enter it in Settings."
)

_AMOUNT = re.compile(
    r"(?:₹|rs\.?|inr)\s*([\d,]+(?:\.\d+)?)\s*(k|lakhs?)?|([\d,]+(?:\.\d+)?)\s*(k|lakhs?|rupees|rs)\b",
    re.IGNORECASE,
)


def parse_amount_rupees(question: str) -> float | None:
    m = _AMOUNT.search(question)
    if not m:
        return None
    raw = (m.group(1) or m.group(3) or "").replace(",", "")
    unit = (m.group(2) or m.group(4) or "").lower()
    try:
        value = float(raw)
    except ValueError:
        return None
    if unit == "k":
        value *= 1_000
    elif unit.startswith("lakh"):
        value *= 100_000
    return value


def answer_can_afford(ctx: FinanceContext, question: str) -> IntentAnswer:
    amount = parse_amount_rupees(question)
    safe = _run(ctx, "safe_to_spend")
    if not safe["available"]:
        return IntentAnswer("can_afford", _NO_BALANCE, [], False, {"safe": safe})
    if amount is None:
        text = (
            f"You can spend up to {inr(safe['safe_total_rupees'])} until the end of the month, "
            f"which is {inr(safe['safe_daily_rupees'])} a day for {safe['days_left']} days. "
            "Tell me the price and I'll check it against that."
        )
        return IntentAnswer("can_afford", text, _safe_facts(safe), False, {"safe": safe})
    check = _run(ctx, "check_affordability", amount_rupees=amount)
    price = inr(check["amount_rupees"])
    if check["verdict"] == "within_today":
        text = (f"Yes. {price} fits within today's safe amount of "
                f"{inr(check['safe_daily_rupees'])}.")
    elif check["verdict"] == "within_month":
        text = (
            f"Yes, but it's more than today's safe amount of {inr(check['safe_daily_rupees'])}. "
            f"Buying it lowers your safe daily amount to {inr(check['safe_daily_after_rupees'])} "
            f"for the remaining {check['days_left']} days."
        )
    else:
        text = (
            f"Not without dipping into upcoming bills or savings. You have "
            f"{inr(check['safe_total_rupees'])} free until month end, so {price} is "
            f"{inr(check['short_by_rupees'])} more than that."
        )
    facts = [Fact(label="Price", value=price)] + _safe_facts(safe)
    return IntentAnswer("can_afford", text, facts, False, {"safe": safe, "check": check})


def _safe_facts(safe: dict) -> list[Fact]:
    return [
        Fact(label="Safe per day", value=inr(safe["safe_daily_rupees"])),
        Fact(label="Safe until month end", value=inr(safe["safe_total_rupees"])),
        Fact(label="Days left", value=str(safe["days_left"])),
    ]


def answer_safe_today(ctx: FinanceContext, _: str) -> IntentAnswer:
    safe = _run(ctx, "safe_to_spend")
    if not safe["available"]:
        return IntentAnswer("safe_to_spend", _NO_BALANCE, [], False, {"safe": safe})
    text = (
        f"You can safely spend {inr(safe['safe_daily_rupees'])} a day for the next "
        f"{safe['days_left']} days ({inr(safe['safe_total_rupees'])} in total). That keeps "
        f"{inr(safe['upcoming_recurring_rupees'])} for upcoming bills and "
        f"{inr(safe['savings_target_rupees'])} for your savings target."
    )
    if safe["status"] == "at_risk":
        text += (f" At your current pace you'd overshoot by about "
                 f"{inr(safe['shortfall_rupees'])}.")
    return IntentAnswer("safe_to_spend", text, _safe_facts(safe), False, {"safe": safe})


def answer_forecast(ctx: FinanceContext, _: str) -> IntentAnswer:
    s = _run(ctx, "month_summary")
    day_to_day = (s["projected_month_end_rupees"] - s["spent_so_far_rupees"]
                  - s["upcoming_recurring_rupees"])
    text = (
        f"At your current pace you'll spend about {inr(s['projected_month_end_rupees'])} this "
        f"month, give or take {inr(s['give_or_take_rupees'])}. That's "
        f"{inr(s['spent_so_far_rupees'])} so far, about {inr(day_to_day)} more in day-to-day "
        f"spending and {inr(s['upcoming_recurring_rupees'])} in upcoming recurring payments."
    )
    facts = [
        Fact(label="Projected month end", value=inr(s["projected_month_end_rupees"])),
        Fact(label="Spent so far", value=inr(s["spent_so_far_rupees"])),
        Fact(label="Upcoming recurring", value=inr(s["upcoming_recurring_rupees"])),
    ]
    return IntentAnswer("forecast", text, facts, False,
                        {"summary": s, "derived": {"day_to_day_rupees": day_to_day}})


def answer_top_spend(ctx: FinanceContext, _: str) -> IntentAnswer:
    data = _run(ctx, "spend_by_category", period="this_month")
    cats = data["categories"][:3]
    if not cats:
        return IntentAnswer("top_spend", "You haven't spent anything this month yet.", [],
                            False, {"spend": data})
    parts = [f"{c['category']} ({inr(c['spent_rupees'])}, {c['share_percent']:.0f}%)"
             for c in cats]
    listed = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
    text = (f"This month you've spent {inr(data['total_rupees'])} so far. "
            f"Most of it went to {listed}.")
    facts = [Fact(label=c["category"], value=inr(c["spent_rupees"])) for c in cats]
    return IntentAnswer("top_spend", text, facts, False, {"spend": data})


# Everyday words for each category. Merchant names are left to the model's
# merchant_spend tool; these only need to catch the common phrasings.
CATEGORY_WORDS: dict[str, str] = {
    "food": r"food|eating out|restaurants?|dining|takeaways?|food delivery",
    "groceries": r"grocer(?:y|ies)|vegetables",
    "transport": r"transport|travel|commut\w*|cabs?|taxis?|fuel|petrol",
    "shopping": r"shopping|clothes",
    "utilities": r"utilit(?:y|ies)|electricity|recharges?|internet|broadband",
    "subscriptions": r"subscriptions?",
    "health": r"health|medicines?|medical|pharmacy|doctors?",
    "entertainment": r"entertainment|movies?|cinema",
    "transfers": r"transfers?",
}
_CATEGORY_RES = {
    cid: re.compile(rf"\b(?:{words})\b", re.I) for cid, words in CATEGORY_WORDS.items()
}
_ALL_CATEGORY_WORDS = "|".join(CATEGORY_WORDS.values())
_PERIOD_TEXT = {"this_month": "this month", "last_month": "last month",
                "last_30_days": "in the last 30 days"}


def _period_in(question: str) -> str:
    q = question.lower()
    if re.search(r"\blast month\b|\bprevious month\b", q):
        return "last_month"
    if re.search(r"\blast 30 days\b|\bpast month\b|\blast four weeks\b", q):
        return "last_30_days"
    return "this_month"


def answer_category_spend(ctx: FinanceContext, question: str) -> IntentAnswer:
    cid = next((c for c, rx in _CATEGORY_RES.items() if rx.search(question)), "other")
    label = ctx.label(cid)
    period = _period_in(question)
    data = _run(ctx, "spend_by_category", period=period)
    row = next((c for c in data["categories"] if c["category"] == label), None)
    when = _PERIOD_TEXT[period]
    if row is None:
        return IntentAnswer("category_spend", f"You haven't spent anything on {label} {when}.",
                            [Fact(label=label, value=inr(0))], False, {"spend": data})
    text = (f"You've spent {inr(row['spent_rupees'])} on {label} {when}, "
            f"{row['share_percent']:.0f}% of your {inr(data['total_rupees'])} total.")
    facts = [Fact(label=label, value=inr(row["spent_rupees"])),
             Fact(label="All spending", value=inr(data["total_rupees"]))]
    return IntentAnswer("category_spend", text, facts, False, {"spend": data})


def _comparison_text(cmp: dict, lead: str) -> str:
    diff = cmp["difference_rupees"]
    rising = [c for c in cmp["categories"] if c["difference_rupees"] > 0][:2]
    if diff > 0:
        text = (f"{lead}You've spent {inr(cmp['this_month_to_date_rupees'])} so far this month, "
                f"{inr(diff)} more than by this date last month "
                f"({inr(cmp['last_month_same_days_rupees'])}).")
        if rising:
            bits = [f"{c['category']} (+{inr(c['difference_rupees'])})" for c in rising]
            text += " The biggest increase" + ("s are " if len(bits) > 1 else " is ") + \
                " and ".join(bits) + "."
        return text
    return (f"You've spent {inr(cmp['this_month_to_date_rupees'])} so far this month, "
            f"{inr(-diff)} less than by this date last month "
            f"({inr(cmp['last_month_same_days_rupees'])}).")


def answer_overspend(ctx: FinanceContext, _: str) -> IntentAnswer:
    cmp = _run(ctx, "compare_with_last_month")
    unusual = _run(ctx, "unusual_payments")
    text = _comparison_text(cmp, "")
    if cmp["difference_rupees"] <= 0:
        text = "You're not overspending compared with last month. " + text
    sensitive = False
    if unusual["items"]:
        u = unusual["items"][0]
        text += (f" There was also an unusual {u['category']} payment of "
                 f"{inr(u['amount_rupees'])} on {day_month(u['date'])}; your "
                 f"{u['category']} payments are usually up to {inr(u['usually_up_to_rupees'])}.")
        sensitive = True
    facts = [
        Fact(label="This month so far", value=inr(cmp["this_month_to_date_rupees"])),
        Fact(label="Same days last month", value=inr(cmp["last_month_same_days_rupees"])),
    ]
    return IntentAnswer("overspend", text, facts, sensitive, {"compare": cmp, "unusual": unusual})


def answer_compare(ctx: FinanceContext, _: str) -> IntentAnswer:
    cmp = _run(ctx, "compare_with_last_month")
    facts = [
        Fact(label="This month so far", value=inr(cmp["this_month_to_date_rupees"])),
        Fact(label="Same days last month", value=inr(cmp["last_month_same_days_rupees"])),
    ]
    return IntentAnswer("compare", _comparison_text(cmp, ""), facts, False, {"compare": cmp})


def answer_recurring(ctx: FinanceContext, _: str) -> IntentAnswer:
    data = _run(ctx, "list_recurring")
    if not data["items"]:
        return IntentAnswer("recurring", "I haven't found any recurring payments yet. I need "
                            "at least three regular payments to spot one.", [], False,
                            {"recurring": data})
    upcoming = data["items"][:3]
    bits = [f"{i['merchant']} ({inr(i['amount_rupees'])}, {day_month(i['next_due'])})"
            for i in upcoming]
    noun = "payment" if data["count"] == 1 else "payments"
    text = (f"You have {data['count']} recurring {noun} costing about "
            f"{inr(data['monthly_total_rupees'])} a month. Next up: " + ", ".join(bits) + ".")
    facts = [Fact(label="Recurring per month", value=inr(data["monthly_total_rupees"]))]
    return IntentAnswer("recurring", text, facts, True, {"recurring": data})


def answer_unusual(ctx: FinanceContext, _: str) -> IntentAnswer:
    data = _run(ctx, "unusual_payments")
    if not data["items"]:
        return IntentAnswer("unusual", "Nothing unusual in the last 30 days.", [], False,
                            {"unusual": data})
    bits = [f"{inr(u['amount_rupees'])} on {u['category']} on {day_month(u['date'])} "
            f"(usually up to {inr(u['usually_up_to_rupees'])})" for u in data["items"][:3]]
    noun = "payment" if data["count"] == 1 else "payments"
    text = f"{data['count']} unusual {noun} in the last 30 days: " + "; ".join(bits) + "."
    return IntentAnswer("unusual", text, [], True, {"unusual": data})


Handler = Callable[[FinanceContext, str], IntentAnswer]

INTENTS: tuple[tuple[str, re.Pattern[str], Handler], ...] = (
    ("can_afford", re.compile(r"\bafford\b|\b(can|could|should) i (buy|get|spend \S+ on)\b",
                              re.I), answer_can_afford),
    ("overspend", re.compile(r"\bover ?spen\w*|\bwhy\b.*\b(spen[dt]|spending)\b.*\b(much|more)\b",
                             re.I), answer_overspend),
    ("top_spend", re.compile(r"\b(where|what)\b.*\b(spen[dt]|spending|money)\b.*\bmost\b|"
                             r"\b(top|biggest|highest|main)\b.*\b(spend\w*|expenses?|categor\w*)",
                             re.I), answer_top_spend),
    ("safe_to_spend", re.compile(r"\bsafe(ly)? to spend\b|\bhow much (can|should|may) i spend\b|"
                                 r"\b(daily|today'?s?) (budget|limit|allowance)\b|"
                                 r"\bleft to spend\b", re.I), answer_safe_today),
    ("category_spend", re.compile(
        rf"\b(?:spen[dt]|spending|paid|expenses?|how much)\b.*\b(?:on|for)\s+(?:my\s+)?"
        rf"(?:{_ALL_CATEGORY_WORDS})\b|\b(?:{_ALL_CATEGORY_WORDS})\s+(?:spen[dt]|spending|expenses?)\b",
        re.I), answer_category_spend),
    ("recurring", re.compile(r"\bsubscriptions?\b|\brecurring\b|\bbills?\b|"
                             r"\bupcoming payments?\b|\brenewals?\b", re.I), answer_recurring),
    ("unusual", re.compile(r"\b(unusual|anomal\w*|suspicious|strange)\b", re.I), answer_unusual),
    ("forecast", re.compile(r"\bend of (the )?month\b|\bmonth[- ]end\b|\bforecast\b|"
                            r"\bproject(ed|ion)\b|\bhow much will i spend\b", re.I),
     answer_forecast),
    ("compare", re.compile(r"\blast month\b|\bprevious month\b|\bcompared?\b", re.I),
     answer_compare),
)

EXAMPLES = (
    "Why did I overspend?",
    "Where did I spend most?",
    "Can I afford a ₹2,000 jacket?",
    "How much can I spend today?",
    "What will I spend by month end?",
    "What subscriptions do I have?",
)


def match(question: str) -> tuple[str, Handler] | None:
    for name, pattern, handler in INTENTS:
        if pattern.search(question):
            return name, handler
    return None
