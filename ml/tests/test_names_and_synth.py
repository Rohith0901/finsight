"""Shared fixtures and synthetic-data sanity checks."""

import json

from finsight_ml import synth
from finsight_ml.baseline import predict as baseline
from finsight_ml.hints import hints_from_body
from finsight_ml.names import is_card_bill_name, resolve
from finsight_ml.paths import FIXTURES


def test_merchant_name_cases_match():
    data = json.loads((FIXTURES / "merchant_name_cases.json").read_text(encoding="utf-8"))
    for case in data["cases"]:
        got = resolve(case["raw"], data["salt"], p2a=case["p2a"], p2m=case["p2m"])
        exp = case["expected"]
        assert (got.kind, got.key, got.category) == (exp["kind"], exp["key"], exp["category"]), case
        assert is_card_bill_name(case["raw"]) == exp["card_bill"], case


def test_hints():
    assert hints_from_body("Rs 649 debited towards NETFLIX UPI AutoPay mandate") == ["autopay"]
    assert "salary" in hints_from_body("NEFT Cr-ACME-SALARY SEP 2026")
    assert "refund" in hints_from_body("Refund of Rs.499.00 from AMAZON credited")


def test_synthetic_data_is_consistent():
    users = synth.generate(n_users=6, seed=1)
    for u in users:
        for t in u.txns:
            exp = t.sms.expected
            assert exp["outcome"] == "transaction"
            assert exp["amount_paise"] == t.amount_paise
            assert exp["direction"] == t.direction
            if t.balance_after is not None:
                assert t.balance_after >= 0, "savings balances never go negative"


def test_baseline():
    assert baseline("swiggy", "", "debit") == "food"
    assert baseline("sharma medical stores", "", "debit") == "health"
    assert baseline("acme technologies", "salary", "credit") == "income"
    assert baseline("sri balaji enterprises", "", "debit") is None
