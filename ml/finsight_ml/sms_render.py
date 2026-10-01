"""Render synthetic transactions as bank-style SMS, with the fields a parser must find.

These formats are approximations of what Indian banks send, written for testing.
They are not copies of real messages and use placeholder phone numbers. A parser
that passes them has only passed formats we wrote ourselves; the team's own
masked messages (ml/data/real) are the real test.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime

from .hints import hints_from_body
from .money import comma, plain1, plain2, plain_int

MON = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

BANK_NAMES = {"hdfc": "HDFC Bank", "sbi": "SBI", "icici": "ICICI Bank", "axis": "Axis Bank",
              "kotak": "Kotak Bank"}
SENDERS = {
    "hdfc": ["VM-HDFCBK", "AD-HDFCBK", "JD-HDFCBK-S", "VK-HDFCBK-T"],
    "sbi": ["VM-SBIUPI", "AD-SBIUPI-S", "BZ-SBIINB", "JM-ATMSBI"],
    "icici": ["VK-ICICIB", "AX-ICICIB-S", "JD-ICICIT"],
    "axis": ["AX-AXISBK", "VM-AXISBK-S", "JD-AXISBK"],
    "kotak": ["VM-KOTAKB", "AD-KOTAKB-S"],
}


def d_slash(t: datetime) -> str:
    return t.strftime("%d/%m/%y")


def d_dash(t: datetime) -> str:
    return t.strftime("%d-%m-%y")


def d_mon(t: datetime) -> str:
    return f"{t.day:02d}-{MON[t.month - 1]}-{t:%y}"


def d_mon_compact(t: datetime) -> str:
    return f"{t.day:02d}{MON[t.month - 1]}{t:%y}"


def d_iso(t: datetime) -> str:
    return t.strftime("%Y-%m-%d")


@dataclass
class Rendered:
    sender: str
    body: str
    template: str
    expected: dict


def _txn_expected(amount, direction, mask, merchant, mode, ref, balance=None, card=None,
                  refund=False, card_bill=False, p2a=False, p2m=False, limit=None) -> dict:
    return {
        "outcome": "transaction",
        "amount_paise": amount,
        "direction": direction,
        "account_mask": mask,
        "card": card,
        "merchant_raw": merchant,
        "mode": mode,
        "ref_no": ref,
        "balance_paise": balance,
        "available_limit_paise": limit,
        "is_refund": refund,
        "is_card_bill": card_bill,
        "p2a": p2a,
        "p2m": p2m,
    }


def _finish(r: Rendered) -> Rendered:
    if r.expected.get("outcome") == "transaction":
        r.expected["hints"] = hints_from_body(r.body)
    return r


# ---------------------------------------------------------------- UPI debit / credit


def upi_debit(rng: random.Random, bank: str, mask: str, amount: int, payee: str, ref: str,
              t: datetime, person: bool) -> Rendered:
    s = rng.choice(SENDERS[bank])
    if bank == "hdfc":
        if rng.random() < 0.5:
            body = (f"Sent Rs.{plain2(amount)}\nFrom HDFC Bank A/C *{mask}\nTo {payee}\n"
                    f"On {d_slash(t)}\nRef {ref}\nNot You?\nCall 18000000000/SMS BLOCK UPI to "
                    f"7000000000")
            tpl = "hdfc_upi_debit_lines"
        else:
            body = (f"Money Sent! Rs {plain2(amount)} from HDFC Bank A/c **{mask} to {payee} on "
                    f"{d_dash(t)}. UPI Ref No {ref}. Not you? Call 18000000000")
            tpl = "hdfc_upi_debit"
        exp = _txn_expected(amount, "debit", mask, payee, "upi", ref)
    elif bank == "sbi":
        body = (f"Dear UPI user A/C X{mask} debited by {plain1(amount)} on date "
                f"{d_mon_compact(t)} trf to {payee} Refno {ref}. If not u? call 1800000000. -SBI")
        tpl = "sbi_upi_debit"
        exp = _txn_expected(amount, "debit", mask, payee, "upi", ref)
    elif bank == "icici":
        m3 = mask[-3:]
        body = (f"ICICI Bank Acct XX{m3} debited for Rs {plain2(amount)} on {d_mon(t)}; "
                f"{payee} credited. UPI:{ref}. Call 18000000000 for dispute. SMS BLOCK {m3} to "
                f"9000000000.")
        tpl = "icici_upi_debit"
        exp = _txn_expected(amount, "debit", m3, payee, "upi", ref)
    elif bank == "axis":
        kind = "P2A" if person else "P2M"
        body = (f"INR {plain2(amount)} debited\nA/c no. XX{mask}\n{d_dash(t)}, {t:%H:%M:%S}\n"
                f"UPI/{kind}/{ref}/{payee}\nNot you? SMS BLOCKUPI Cust ID to 919000000000\n"
                f"Axis Bank")
        tpl = "axis_upi_debit"
        exp = _txn_expected(amount, "debit", mask, payee, "upi", ref, p2a=person, p2m=not person)
    else:
        body = (f"Sent Rs.{plain2(amount)} from Kotak Bank AC X{mask} to {payee} on "
                f"{d_dash(t)}.UPI Ref {ref}. Not you, call 18000000000")
        tpl = "kotak_upi_debit"
        exp = _txn_expected(amount, "debit", mask, payee, "upi", ref)
    return _finish(Rendered(s, body, tpl, exp))


def upi_credit(rng: random.Random, bank: str, mask: str, amount: int, payer: str, ref: str,
               t: datetime, balance: int, person: bool) -> Rendered:
    s = rng.choice(SENDERS[bank])
    if bank == "hdfc":
        body = (f"Money Received! Rs {plain2(amount)} in HDFC Bank A/c **{mask} from {payer} on "
                f"{d_dash(t)}. UPI Ref No {ref}. Avl bal Rs {comma(balance)}")
        tpl, exp = "hdfc_upi_credit", _txn_expected(amount, "credit", mask, payer, "upi", ref,
                                                   balance=balance)
    elif bank == "sbi":
        body = (f"Dear SBI User, your A/c X{mask}-credited by Rs.{plain_int(amount)} on "
                f"{d_mon_compact(t)} transfer from {payer} Ref No {ref} -SBI")
        # This format never says "UPI", so the parser cannot know the channel.
        tpl, exp = "sbi_upi_credit", _txn_expected(amount, "credit", mask, payer,
                                                   "upi" if "@" in payer else "other", ref)
    elif bank == "icici":
        m3 = mask[-3:]
        body = (f"Dear Customer, Acct XX{m3} is credited with Rs {plain2(amount)} on {d_mon(t)} "
                f"from {payer}. UPI:{ref}-ICICI Bank.")
        tpl, exp = "icici_upi_credit", _txn_expected(amount, "credit", m3, payer, "upi", ref)
    elif bank == "axis":
        kind = "P2A" if person else "P2M"
        body = (f"INR {plain2(amount)} credited\nA/c no. XX{mask}\n{d_dash(t)}, {t:%H:%M:%S}\n"
                f"UPI/{kind}/{ref}/{payer}\nNot you? SMS BLOCKUPI Cust ID to 919000000000\n"
                f"Axis Bank")
        tpl, exp = "axis_upi_credit", _txn_expected(amount, "credit", mask, payer, "upi", ref,
                                                   p2a=person, p2m=not person)
    else:
        body = (f"Received Rs.{plain2(amount)} in your Kotak Bank AC X{mask} from {payer} on "
                f"{d_dash(t)}.UPI Ref:{ref}.")
        tpl, exp = "kotak_upi_credit", _txn_expected(amount, "credit", mask, payer, "upi", ref)
    return _finish(Rendered(s, body, tpl, exp))


def upi_autopay(rng: random.Random, bank: str, mask: str, amount: int, payee: str, ref: str,
                t: datetime) -> Rendered:
    name = BANK_NAMES[bank]
    body = (f"Rs.{plain2(amount)} debited from {name} A/c XX{mask} towards {payee} for UPI "
            f"AutoPay mandate on {d_dash(t)}. UPI Ref No {ref}.")
    return _finish(Rendered(rng.choice(SENDERS[bank]), body, "autopay_debit",
                            _txn_expected(amount, "debit", mask, payee, "upi", ref)))


# ---------------------------------------------------------------- cards


def debit_card(rng: random.Random, bank: str, mask4: str, amount: int, merchant: str,
               t: datetime, balance: int) -> Rendered:
    s = rng.choice(SENDERS[bank])
    if bank == "hdfc":
        body = (f"Spent Rs.{plain2(amount)} On HDFC Bank Card {mask4} At {merchant} On "
                f"{d_iso(t)}:{t:%H:%M:%S} Bal Rs.{plain2(balance)} Not You? Call 18000000000/SMS "
                f"BLOCK DC {mask4} to 7000000000")
        tpl = "hdfc_debit_card"
    elif bank == "sbi":
        body = (f"Dear Customer, your SBI Debit Card ending {mask4} was used for Rs.{plain2(amount)} "
                f"at {merchant} on {d_slash(t)}. Avl Bal Rs.{plain2(balance)}. If not done by you, "
                f"call 1800000000 -SBI")
        tpl = "sbi_debit_card"
    else:
        body = (f"{BANK_NAMES[bank]} Debit Card XX{mask4} used for Rs {plain2(amount)} at "
                f"{merchant} on {d_dash(t)}. Avl Bal Rs {comma(balance)}.")
        tpl = "generic_debit_card"
    exp = _txn_expected(amount, "debit", mask4, merchant, "card", None, balance=balance,
                        card="debit")
    return _finish(Rendered(s, body, tpl, exp))


def credit_card(rng: random.Random, bank: str, mask4: str, amount: int, merchant: str,
                t: datetime, limit: int) -> Rendered:
    s = rng.choice(SENDERS[bank])
    if bank == "hdfc":
        body = (f"Rs.{plain2(amount)} spent on HDFC Bank Credit Card xx{mask4} at {merchant} on "
                f"{d_dash(t)}. Avl Lmt: Rs {comma(limit)}. Not you? Call 18000000000")
        tpl = "hdfc_credit_card"
    elif bank == "icici":
        body = (f"INR {comma(amount)} spent using ICICI Bank Card XX{mask4} on {d_mon(t)} on "
                f"{merchant}. Avl Limit: INR {comma(limit)}. If not you, call 1800 000 0000/SMS "
                f"BLOCK {mask4} to 9000000000")
        tpl = "icici_credit_card"
    elif bank == "axis":
        body = (f"Spent\nCard no. XX{mask4}\nINR {plain2(amount)}\n{d_dash(t)} {t:%H:%M:%S}\n"
                f"{merchant}\nAvl Lmt INR {comma(limit)}\nSMS BLOCK {mask4} to 919000000000\n"
                f"Axis Bank")
        tpl = "axis_credit_card"
    else:
        body = (f"Rs.{plain2(amount)} spent on {BANK_NAMES[bank]} Credit Card XX{mask4} at "
                f"{merchant} on {d_dash(t)}. Avl Lmt Rs {comma(limit)}.")
        tpl = "generic_credit_card"
    exp = _txn_expected(amount, "debit", mask4, merchant, "card", None, card="credit",
                        limit=limit)
    return _finish(Rendered(s, body, tpl, exp))


def card_payment_received(rng: random.Random, bank: str, mask4: str, amount: int,
                          t: datetime) -> Rendered:
    body = (f"Payment of Rs.{plain2(amount)} has been received towards your {BANK_NAMES[bank]} "
            f"Credit Card xx{mask4} on {d_dash(t)}. Thank you.")
    exp = _txn_expected(amount, "credit", mask4, None, "other", None, card="credit",
                        card_bill=True)
    return _finish(Rendered(rng.choice(SENDERS[bank]), body, "card_payment_received", exp))


# ---------------------------------------------------------------- NEFT, refunds


def neft_credit(rng: random.Random, bank: str, mask: str, amount: int, payer: str, utr: str,
                narration: str, t: datetime, balance: int) -> Rendered:
    s = rng.choice(SENDERS[bank])
    if bank == "hdfc":
        body = (f"Update! INR {comma(amount)} deposited in HDFC Bank A/c XX{mask} on {d_mon(t)} "
                f"for NEFT Cr-CITI0000001-{payer}-{narration}-{utr}. Avl bal INR "
                f"{comma(balance)}. Cheque deposits in A/C are subject to clearing")
        tpl = "hdfc_neft_credit"
    elif bank == "sbi":
        body = (f"Your A/C XXXXX{mask} has credit for NEFT transfer of Rs {plain2(amount)} on "
                f"{d_slash(t)} by {payer} ({narration}). Ref {utr}. Avl Bal Rs "
                f"{plain2(balance)}-SBI")
        tpl = "sbi_neft_credit"
    else:
        body = (f"INR {comma(amount)} credited to your A/c XX{mask} on {d_mon(t)} by NEFT from "
                f"{payer} ({narration}). Ref {utr}. Avl Bal INR {comma(balance)}")
        tpl = "generic_neft_credit"
    exp = _txn_expected(amount, "credit", mask, payer, "neft", utr, balance=balance)
    return _finish(Rendered(s, body, tpl, exp))


def refund_credit(rng: random.Random, bank: str, mask: str, amount: int, merchant: str,
                  ref: str, t: datetime) -> Rendered:
    s = rng.choice(SENDERS[bank])
    if bank == "icici":
        m3 = mask[-3:]
        body = (f"Dear Customer, your ICICI Bank Acct XX{m3} has been credited with INR "
                f"{comma(amount)} on {d_mon(t)} as a refund from {merchant}. Ref {ref}.")
        exp = _txn_expected(amount, "credit", m3, merchant, "other", ref, refund=True)
        tpl = "icici_refund"
    else:
        body = (f"Refund of Rs.{plain2(amount)} from {merchant} credited to your "
                f"{BANK_NAMES[bank]} A/c XX{mask} on {d_dash(t)}. Ref {ref}.")
        exp = _txn_expected(amount, "credit", mask, merchant, "other", ref, refund=True)
        tpl = "generic_refund"
    return _finish(Rendered(s, body, tpl, exp))


# ---------------------------------------------------------------- not transactions


def noise(rng: random.Random, bank: str, mask: str, mask4: str, t: datetime) -> Rendered:
    """Messages from bank senders that must NOT become transactions."""
    name = BANK_NAMES[bank]
    amount = rng.randrange(20_000, 900_000, 100)
    otp = f"{rng.randrange(100000, 999999)}"
    ref = f"{rng.randrange(10**11, 10**12)}"
    options = [
        ("otp_card", f"{otp} is the OTP for txn of Rs {plain2(amount)} at AMAZON on your {name} "
                     f"Card ending {mask4}. Valid for 10 mins. Do not share it with anyone.",
         "otp"),
        ("otp_online", f"OTP for online payment of Rs.{comma(amount)} at FLIPKART is {otp}. "
                       f"Never share OTP with anyone. -{name}", "otp"),
        ("collect_request", f"PRIYA S has requested money from you on UPI. On approving, Rs "
                            f"{plain2(amount)} will be debited from your A/c. Ignore if not "
                            f"known. -{name}", "request"),
        ("declined", f"Transaction of Rs {plain2(amount)} at MYNTRA on your {name} card ending "
                     f"{mask4} has been declined due to insufficient balance.", "declined"),
        ("mandate_notice", f"Rs {plain2(amount)} will be debited from your A/c XX{mask} on "
                           f"{d_dash(t)} towards NETFLIX for UPI AutoPay mandate. Ref {ref}.",
         "future"),
        ("card_due", f"Payment of Rs {comma(amount)} is due on your {name} Credit Card XX{mask4} "
                     f"by {d_dash(t)}. Minimum due Rs {comma(amount // 20)}. Pay now to avoid "
                     f"charges.", "due"),
    ]
    tpl, body, reason = rng.choice(options)
    return Rendered(rng.choice(SENDERS[bank]), body, tpl, {"outcome": "rejected", "reason": reason})


def promo(rng: random.Random, bank: str) -> Rendered:
    name = BANK_NAMES[bank]
    body = rng.choice([
        f"Pre-approved Personal Loan of Rs 5,00,000 is waiting for you! Apply now in 2 mins. "
        f"T&C apply -{name}",
        f"Get 10% cashback up to Rs 1,500 on your {name} card this festive season. Offer valid "
        f"till 31-10-26. T&C",
    ])
    sender = rng.choice(SENDERS[bank]).split("-")[0] + "-" + \
        rng.choice(SENDERS[bank]).split("-")[1] + "-P"
    return Rendered(sender, body, "promo", {"outcome": "rejected", "reason": "promo"})


def balance_only(rng: random.Random, bank: str, mask: str, balance: int, t: datetime) -> Rendered:
    body = (f"Available balance in your A/c XX{mask} is Rs {comma(balance)} as on {d_dash(t)}. "
            f"-{BANK_NAMES[bank]}")
    return Rendered(rng.choice(SENDERS[bank]), body, "balance_only",
                    {"outcome": "balance", "account_mask": mask, "balance_paise": balance})


def personal(rng: random.Random) -> Rendered:
    body = rng.choice(["Reached home? Call me when free.", "Pay 250 for the cab tomorrow ok",
                       "Your OTP from me lol 1234"])
    return Rendered(f"+9198{rng.randrange(10**7, 10**8)}", body, "personal",
                    {"outcome": "skipped"})
