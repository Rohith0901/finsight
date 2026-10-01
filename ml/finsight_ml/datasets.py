"""Turn synthetic users into the datasets each part of the system needs."""

from __future__ import annotations

import json
import random
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

from finsight_api.schemas import Txn as ApiTxn

from .synth import Txn, User

RULE_INCOME_HINTS = {"salary", "interest", "cashback"}


def is_classifiable(t: Txn) -> bool:
    """Rows the model would see. The phone's rules (app/lib/ingestion/pipeline.dart)
    already handle persons, self transfers, card payments and hinted income."""
    return (
        not t.is_self_transfer
        and not t.merchant_norm.startswith("person:")
        and t.channel != "card_payment"
        and not (t.direction == "credit" and RULE_INCOME_HINTS & set(t.descriptor.split()))
    )


def classifier_rows(users: list[User]) -> list[dict]:
    rows = []
    for u in users:
        for t in u.txns:
            if not is_classifiable(t):
                continue
            rows.append({
                "user_id": u.uid,
                "merchant_norm": t.merchant_norm,
                "descriptor": t.descriptor,
                "mode": t.mode,
                "direction": t.direction,
                "amount_paise": t.amount_paise,
                "category": t.category,
                # Grouped splits use the true merchant, so a test merchant is never seen in
                # training, even when its SMS only showed an anonymous QR handle.
                "group": t.merchant_identity if not t.merchant_identity.startswith("person:")
                else "person",
                "known": bool(t.merchant_norm) and t.merchant_norm == t.merchant_identity,
            })
    return rows


def api_txn(t: Txn, category: str | None = None) -> ApiTxn:
    return ApiTxn(
        id=t.txn_id,
        ts=t.ts,
        amount_paise=t.amount_paise,
        direction=t.direction,
        merchant_norm=t.merchant_norm,
        category=category if category is not None else t.category,
        account_alias=t.account.alias,
        mode=t.mode if t.mode in ("upi", "card", "neft", "imps", "rtgs", "atm", "netbanking")
        else "other",
        is_self_transfer=t.is_self_transfer,
        is_refund=t.is_refund,
    )


def api_window(u: User, before: date | None = None) -> list[ApiTxn]:
    return [api_txn(t) for t in u.txns if before is None or t.ts.date() < before]


def _sms_line(i: int, sender: str, body: str, ts: datetime, template: str, expected: dict) -> dict:
    return {"id": f"s{i:05d}", "sender": sender, "body": body,
            "received_at": ts.isoformat(timespec="seconds"), "template": template,
            "expected": expected}


def write_parser_fixtures(users: list[User], noise, path: Path, per_template: int = 30,
                          seed: int = 5) -> int:
    """A stratified sample: every template, including every kind of message to reject."""
    rng = random.Random(seed)
    by_template: dict[str, list[Txn]] = defaultdict(list)
    for u in users:
        for t in u.txns:
            by_template[t.sms.template].append(t)
    lines = []
    for template in sorted(by_template):
        for t in rng.sample(by_template[template], min(per_template, len(by_template[template]))):
            lines.append(_sms_line(len(lines), t.sms.sender, t.sms.body, t.ts, template,
                                   t.sms.expected))
    for _, msg, ts in noise:
        lines.append(_sms_line(len(lines), msg.sender, msg.body, ts, msg.template, msg.expected))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for line in lines:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    return len(lines)


def write_demo_sms(user: User, noise, path: Path, months: int = 3) -> int:
    """One user's last few months, for the app's demo mode (dates are shifted on load)."""
    last = max(t.ts for t in user.txns)
    cutoff = date(last.year, last.month, 1)
    for _ in range(months - 1):
        cutoff = date(cutoff.year - (cutoff.month == 1), (cutoff.month - 2) % 12 + 1, 1)
    items = [(t.ts, t.sms.sender, t.sms.body) for t in user.txns if t.ts.date() >= cutoff]
    items += [(ts, m.sender, m.body) for u, m, ts in noise if u is user and ts.date() >= cutoff]
    items.sort()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for ts, sender, body in items:
            f.write(json.dumps({"sender": sender, "body": body,
                                "received_at": ts.isoformat(timespec="seconds")},
                               ensure_ascii=False) + "\n")
    return len(items)
