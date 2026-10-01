"""Reference SMS parser: the same algorithm as app/lib/ingestion/sms_parser.dart.

The product parser runs on the phone in Dart. This Python twin exists so the
algorithm can be tested here against shared/fixtures, and so exported real
messages can be scored offline:  python -m finsight_ml.parser_ref <fixtures.jsonl>
Keep the two in step; each regex below has the same name in the Dart file.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field

from .hints import hints_from_body

# ASCII mode: Dart RegExp is ASCII-only for \b, \w, \d and case folding.
I = re.IGNORECASE | re.ASCII  # noqa: E741

# ---------------------------------------------------------------- senders

PERSONAL_SENDER = re.compile(r"^\+?[0-9]{10,13}$")
BANK_HEADERS = {
    "HDFCBK": "hdfc", "HDFCBN": "hdfc", "SBIUPI": "sbi", "SBIINB": "sbi", "ATMSBI": "sbi",
    "SBIPSG": "sbi", "CBSSBI": "sbi", "SBICRD": "sbi", "ICICIB": "icici", "ICICIT": "icici",
    "AXISBK": "axis", "AXISMR": "axis", "KOTAKB": "kotak", "PNBSMS": "pnb", "BOIIND": "boi",
    "BOBTXN": "bob", "BOBSMS": "bob", "CANBNK": "canara", "UNIONB": "union", "IDFCFB": "idfc",
    "INDUSB": "indusind", "YESBNK": "yes", "FEDBNK": "federal", "AUBANK": "au",
    "PAYTMB": "paytm", "AIRBNK": "airtel", "RBLBNK": "rbl", "CENTBK": "central",
    "SCBANK": "sc", "HSBCIN": "hsbc", "CITIBK": "citi", "AMEXIN": "amex",
}


@dataclass
class Sender:
    kind: str  # "bank" | "unknown" | "personal" | "promotional"
    bank: str | None = None
    header: str = ""


def classify_sender(raw: str) -> Sender:
    s = raw.strip().upper().replace(" ", "")
    if PERSONAL_SENDER.match(s):
        return Sender("personal")
    parts = s.split("-")
    suffix = parts[-1] if len(parts) > 1 and len(parts[-1]) == 1 else ""
    if suffix == "P":
        return Sender("promotional")
    candidates = [p for p in parts if len(p) == 6 and p.isalnum()]
    header = candidates[-1] if candidates else (s if len(s) == 6 else "")
    if header in BANK_HEADERS:
        return Sender("bank", BANK_HEADERS[header], header)
    return Sender("unknown", None, header)


# ---------------------------------------------------------------- patterns

AMT = r"([0-9][0-9,]*(?:\.[0-9]{1,2})?)"
CUR = r"(?:rs\.?|inr|₹)"
CURRENCY_AMOUNT = re.compile(CUR + r"\s*" + AMT, I)
VERB_AMOUNT = re.compile(r"(?:debited|credited)\s+(?:by|for|with)\s+" + CUR + r"?\s*" + AMT, I)
BALANCE_BEFORE = re.compile(r"(?:bal|balance|lmt|limit|avl|avbl|available)[^0-9]{0,12}$", I)
BALANCE = re.compile(
    r"(?:(?:avl|avbl|available)\.?\s*bal(?:ance)?|\bbal)\.?\s*(?:is\s*)?[:\-]?\s*" + CUR + r"?\s*" + AMT, I)
BALANCE_ONLY = re.compile(
    r"balance in (?:your )?a/c\s*\S+\s+is\s+" + CUR + r"\s*" + AMT, I)
AVAILABLE_LIMIT = re.compile(r"(?:avl|available)\.?\s*(?:lmt|limit)\s*:?\s*" + CUR + r"?\s*" + AMT, I)

DEBIT_VERB = re.compile(r"\b(debited|debit(?!\s*card)|spent|sent|paid|withdrawn|used for|purchase)\b", I)
CREDIT_VERB = re.compile(r"\b(credited|credit(?!\s*card)|received|deposited|refund(?:ed)?|reversed|reversal)\b", I)
COMPLETED_VERB = re.compile(r"\b(debited|credited|spent|sent|withdrawn|deposited|received|refunded|reversed|paid|has credit|used for)\b", I)

CARD_MASK = re.compile(r"\bcard\s*(?:no\.?|number)?\s*(?:ending(?:\s*with)?)?\s*[x*]*\s*([0-9]{4})\b", I)
CREDIT_CARD = re.compile(r"credit\s*card|(?:avl|available)\.?\s*(?:lmt|limit)", I)
ACCOUNT_MASK = re.compile(r"(?:a/c|acct|account|\bac)\.?\s*(?:no\.?)?\s*[:\-]?\s*(?:[x*]+|\.\.)?\s*([0-9]{3,6})\b", I)

AXIS_UPI_REF = re.compile(r"UPI/P2[AM]/([0-9]{6,})/", I)
REF = re.compile(
    r"\b(?:upi\s*ref(?:erence)?\s*(?:no\.?|number)?|ref(?:erence)?\s*(?:no\.?|number|#)?|refno|rrn|"
    r"utr(?:\s*no\.?)?|txn\s*(?:id|no\.?))\s*[:.\-]?\s*([A-Za-z0-9]{6,25})", I)
UPI_COLON_REF = re.compile(r"\bupi\s*:\s*([0-9]{6,})", I)
HDFC_NEFT = re.compile(r"NEFT\s*Cr-[A-Za-z0-9]+-(.+?)-.+-([A-Za-z0-9]{8,})(?:\.|\s|$)", I)

AXIS_UPI_PARTY = re.compile(r"UPI/P2([AM])/[0-9]+/([^\n/]+)", I)
AXIS_CARD_LINES = re.compile(r"^Spent\nCard no\.[^\n]*\n[^\n]*\n[^\n]*\n([^\n]+)", I)
TO_LINE = re.compile(r"^To (.+)$", I | re.M)
ICICI_UPI_PAYEE = re.compile(r";\s*(.+?)\s+credited", I)
ICICI_CARD_PAYEE = re.compile(r"\bon\s+\d{1,2}-[A-Za-z]{3}-\d{2}\s+on\s+(.+?)\.\s*avl", I)
VPA_TO = re.compile(r"\bto\s+(?:vpa\s+)?([A-Za-z0-9._\-]+@[A-Za-z0-9.\-]+)", I)
VPA_FROM = re.compile(r"\bfrom\s+(?:vpa\s+)?([A-Za-z0-9._\-]+@[A-Za-z0-9.\-]+)", I)
_END = r"(?=\s+on\b|\s+ref|\s+upi\b|\s+via\b|\s+for\b|\s+at\b|\s+towards\b|\.(?:\s|$)|,|\n|$)"
AT_PAYEE = re.compile(r"\bat\s+(.+?)(?=\s+on\b|\s+via\b|\s+avl\b|\.(?:\s|$)|\n|$)", I)
TOWARDS_PAYEE = re.compile(r"\btowards\s+(.+?)" + _END, I)
TO_PAYEE = re.compile(r"\b(?:trf to|transfer to|paid to|sent to|to)\s+(.+?)" + _END, I)
_CREDIT_END = r"(?=\s+on\b|\s+ref|\s+upi\b|\s+via\b|\s+credited\b|\s*\(|\.(?:\s|$)|,|\n|$)"
FROM_PAYER = re.compile(r"\bfrom\s+(.+?)" + _CREDIT_END, I)
BY_PAYER = re.compile(r"\bby\s+(.+?)" + _CREDIT_END, I)
BAD_PARTY = re.compile(r"^(your|the|a/c|ac)\b|a/c|\bacct\b|\bcard\b|\bbank a", I)

CARD_BILL_CREDIT = re.compile(r"payment\b.*\breceived|received towards", I)

OTP = re.compile(r"\botp\b|one[\s-]?time password|verification code", I)
REQUEST = re.compile(r"requested money|collect request|request(?:ed)? (?:of|for) (?:rs|inr|₹)", I)
FUTURE = re.compile(r"will be (?:debited|credited|deducted)|\bis due\b|\bdue (?:on|by)\b|due date|scheduled for", I)
DECLINED = re.compile(r"declined|\bfailed\b|unsuccessful|could not be processed|not processed", I)
PROMO = re.compile(r"pre-?approved|apply now|offer valid|\bt&c\b|cashback up to|limited period|click here", I)


def to_paise(text: str) -> int:
    whole, _, frac = text.replace(",", "").partition(".")
    return int(whole) * 100 + int((frac + "00")[:2])


@dataclass
class Parsed:
    outcome: str  # "transaction" | "balance" | "rejected" | "skipped" | "miss"
    reason: str = ""
    amount_paise: int | None = None
    direction: str | None = None
    account_mask: str | None = None
    card: str | None = None
    merchant_raw: str | None = None
    mode: str = "other"
    ref_no: str | None = None
    balance_paise: int | None = None
    available_limit_paise: int | None = None
    is_refund: bool = False
    is_card_bill: bool = False
    p2a: bool = False
    p2m: bool = False
    hints: list[str] = field(default_factory=list)


def _amount(body: str) -> int | None:
    for m in CURRENCY_AMOUNT.finditer(body):
        if not BALANCE_BEFORE.search(body[max(0, m.start() - 25):m.start()]):
            return to_paise(m.group(1))
    m = VERB_AMOUNT.search(body)
    return to_paise(m.group(1)) if m else None


def _direction(body: str) -> str | None:
    d, c = DEBIT_VERB.search(body), CREDIT_VERB.search(body)
    if d and (not c or d.start() < c.start()):
        return "debit"
    return "credit" if c else None


def _clean_party(text: str | None) -> str | None:
    if not text:
        return None
    t = text.strip().rstrip(".,;:").strip()
    if not t or len(t) > 60 or not re.search(r"[A-Za-z]", t) or BAD_PARTY.search(t):
        return None
    return t


def _first(patterns, body: str, group: int = 1) -> str | None:
    for p in patterns:
        m = p.search(body)
        if m:
            party = _clean_party(m.group(group))
            if party:
                return party
    return None


def parse(sender_raw: str, body: str) -> Parsed:
    sender = classify_sender(sender_raw)
    if sender.kind == "personal":
        return Parsed("skipped", "personal sender")
    if sender.kind == "promotional":
        return Parsed("rejected", "promo")
    body = body.replace("\r\n", "\n").replace("\r", "\n")
    completed = COMPLETED_VERB.search(body) is not None
    for pattern, reason in ((REQUEST, "request"), (FUTURE, "future"), (DECLINED, "declined")):
        if pattern.search(body):
            return Parsed("rejected", reason)
    if not completed and OTP.search(body):
        return Parsed("rejected", "otp")
    if not completed and PROMO.search(body):
        return Parsed("rejected", "promo")
    if not completed:
        m = BALANCE_ONLY.search(body) or BALANCE.search(body)
        acct = ACCOUNT_MASK.search(body)
        if m and acct:
            return Parsed("balance", account_mask=acct.group(1), balance_paise=to_paise(m.group(1)))

    amount, direction = _amount(body), _direction(body)
    if amount is None or direction is None:
        return Parsed("miss", "no amount" if amount is None else "no direction")

    p = Parsed("transaction", amount_paise=amount, direction=direction)
    card = CARD_MASK.search(body)
    if card:
        p.account_mask = card.group(1)
        p.card = "credit" if CREDIT_CARD.search(body) else "debit"
    else:
        acct = ACCOUNT_MASK.search(body)
        p.account_mask = acct.group(1) if acct else None

    m = AXIS_UPI_REF.search(body)
    if m:
        p.ref_no = m.group(1)
    else:
        neft = HDFC_NEFT.search(body)
        if neft:
            p.ref_no = neft.group(2)
        else:
            for pattern in (REF, UPI_COLON_REF):
                for r in pattern.finditer(body):
                    if re.search(r"[0-9]", r.group(1)):
                        p.ref_no = r.group(1)
                        break
                if p.ref_no:
                    break

    bal = BALANCE.search(body)
    p.balance_paise = to_paise(bal.group(1)) if bal else None
    lim = AVAILABLE_LIMIT.search(body)
    p.available_limit_paise = to_paise(lim.group(1)) if lim else None

    axis = AXIS_UPI_PARTY.search(body)
    if axis:
        p.merchant_raw = _clean_party(axis.group(2))
        p.p2a, p.p2m = axis.group(1).upper() == "A", axis.group(1).upper() == "M"
    elif direction == "credit" and p.card:
        p.merchant_raw = None  # a payment received on a card has no merchant
    elif direction == "credit":
        neft = HDFC_NEFT.search(body)
        p.merchant_raw = _clean_party(neft.group(1)) if neft else _first(
            (VPA_FROM, FROM_PAYER, BY_PAYER), body)
    else:
        p.merchant_raw = _first((AXIS_CARD_LINES, TO_LINE, ICICI_UPI_PAYEE, ICICI_CARD_PAYEE,
                                 VPA_TO, AT_PAYEE, TOWARDS_PAYEE, TO_PAYEE), body)

    lower = body.lower()
    if re.search(r"\bupi\b", lower, re.A) or "@" in body:
        p.mode = "upi"
    elif re.search(r"\bneft\b", lower, re.A):
        p.mode = "neft"
    elif re.search(r"\bimps\b", lower, re.A):
        p.mode = "imps"
    elif re.search(r"\brtgs\b", lower, re.A):
        p.mode = "rtgs"
    elif re.search(r"\batm\b", lower, re.A):
        p.mode = "atm"
    elif re.search(r"net ?banking", lower, re.A):
        p.mode = "netbanking"
    elif p.card and direction == "debit":
        p.mode = "card"
    p.hints = hints_from_body(body)
    p.is_refund = direction == "credit" and "refund" in p.hints
    p.is_card_bill = direction == "credit" and p.card is not None and bool(
        CARD_BILL_CREDIT.search(body))
    return p


COMPARED = ("amount_paise", "direction", "account_mask", "card", "merchant_raw", "mode", "ref_no",
            "balance_paise", "available_limit_paise", "is_refund", "is_card_bill", "p2a", "p2m",
            "hints")


def check(line: dict) -> list[str]:
    """Differences between the parser and a fixture's expectation."""
    exp = line["expected"]
    got = parse(line["sender"], line["body"])
    if got.outcome != exp["outcome"]:
        return [f"outcome {got.outcome}({got.reason}) != {exp['outcome']}"]
    diffs = []
    keys = COMPARED if exp["outcome"] == "transaction" else (
        ("account_mask", "balance_paise") if exp["outcome"] == "balance" else ())
    for k in keys:
        if k in exp:
            want, have = exp[k], getattr(got, k)
            if k == "merchant_raw" and want and have:
                want, have = want.lower(), have.lower()
            if want != have:
                diffs.append(f"{k}: {have!r} != {want!r}")
    return diffs


def main(path: str) -> None:
    with open(path, encoding="utf-8") as f:
        lines = [json.loads(x) for x in f if x.strip()]
    bad = [(ln, d) for ln in lines if (d := check(ln))]
    for ln, d in bad[:40]:
        print(ln["template"], "|", d, "\n   ", ln["body"].replace("\n", " / "))
    print(f"{len(lines) - len(bad)}/{len(lines)} fixtures parsed exactly")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "../shared/fixtures/sms_synthetic.jsonl")
