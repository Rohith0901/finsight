"""The Python reference parser must match every shared fixture exactly.

The Dart parser in app/lib/ingestion/sms_parser.dart is a line-for-line port
of parser_ref, so this test is the cheapest guard on both: if a template or a
regex changes, the fixtures, parser_ref and the Dart port must move together.
"""

import json

from finsight_ml.parser_ref import check, classify_sender, to_paise
from finsight_ml.paths import SHARED

FIXTURES = SHARED / "fixtures" / "sms_synthetic.jsonl"


def _lines():
    with open(FIXTURES, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def test_every_fixture_parses_exactly():
    lines = _lines()
    assert len(lines) > 1000
    bad = [(ln["id"], ln["template"], d) for ln in lines if (d := check(ln))]
    assert not bad, f"{len(bad)} fixtures differ, first: {bad[:5]}"


def test_every_template_is_covered():
    templates = {ln["template"] for ln in _lines()}
    outcomes = {ln["expected"]["outcome"] for ln in _lines()}
    assert len(templates) >= 20
    assert {"transaction", "balance", "rejected", "skipped"} <= outcomes


def test_bank_remarks_are_cut_from_payee_names():
    from finsight_ml.parser_ref import _clean_party
    # Seen on a real phone: the name, then the bank's remark and reference.
    assert _clean_party("J JOTHIMANI Info:P2A/624107654321") == "J JOTHIMANI"
    assert _clean_party("RAHUL K/P2M/512345") == "RAHUL K"
    assert _clean_party("Infosys Ltd") == "Infosys Ltd"
    assert _clean_party("q123456789@ybl") == "q123456789@ybl"


def test_amounts_and_senders():
    assert to_paise("45,000.50") == 4500050
    assert to_paise("1,00,000") == 10000000
    assert classify_sender("VM-HDFCBK").kind == "bank"
    assert classify_sender("+919876543210").kind == "personal"
