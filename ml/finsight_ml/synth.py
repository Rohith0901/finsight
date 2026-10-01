"""Synthetic users, transactions and SMS for training and regression tests.

Six months (March to August 2026) for students and young professionals. Every
transaction keeps its ground truth: category, recurring series, anomaly flag,
refund and self-transfer flags. Rendered SMS go to shared/fixtures for the Dart
parser tests; the classifier trains on the features the phone would send.

Synthetic data is for training volume, regression tests and injected-anomaly
evaluation. Headline numbers come only from the team's real, masked messages.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone

from . import sms_render as R
from .hints import descriptor
from .names import is_card_bill_name, resolve, rules

IST = timezone(timedelta(hours=5, minutes=30))
START = date(2026, 3, 1)
END = date(2026, 8, 31)
DATASET_VERSION = "synth-2026.09"
SALT = "synthetic-salt"

FIRST = ["Rahul", "Priya", "Arjun", "Sneha", "Karthik", "Divya", "Aditya", "Ananya", "Rohan", "Meera", "Vikram", "Kavya", "Siddharth", "Pooja", "Nikhil", "Aishwarya", "Harish", "Lakshmi", "Suresh", "Deepa", "Manoj", "Swathi", "Varun", "Nandini", "Ajay", "Riya", "Farhan", "Sana", "Imran", "Zoya", "Gurpreet", "Simran", "Joseph", "Anita"]
LAST = ["Sharma", "Verma", "Iyer", "Nair", "Reddy", "Rao", "Patel", "Gupta", "Singh", "Kumar", "Menon", "Das", "Joshi", "Kulkarni", "Shetty", "Pillai", "Bose", "Chatterjee", "Khan", "Ahmed", "Fernandes", "Dsouza", "Mehta", "Shah", "Naidu", "Hegde"]
PREFIX = ["Sri", "Shree", "Sai", "Balaji", "Krishna", "Ganesh", "Lakshmi", "Om", "New", "Royal", "City", "Annapurna", "Sharma", "Gupta", "Patel", "Reddy", "Iyer", "Nair", "Star", "Golden", "Green", "Metro", "National", "Modern", "Janata", "Bharat", "Venkateswara", "Murugan", "Saraswati", "Durga", "Maruti", "Jai", "Anand", "Vijaya", "Sagar", "Kaveri", "Ganga", "Surya", "Ashoka", "Vishnu", "Kamakshi"]
LONG_TAIL = {
    "food": ["Tea Stall", "Tiffin Centre", "Bakery", "Sweets", "Canteen", "Juice Centre",
             "Biryani House", "Dhaba", "Restaurant", "Cafe", "Chaat Bhandar", "Idli House", "Mess",
             "Food Court", "Bhojanalaya", "Coffee House", "Momos Corner", "Family Restaurant"],
    "groceries": ["Kirana Store", "Provision Store", "General Store", "Supermarket", "Fresh Mart",
                  "Vegetables", "Dairy", "Departmental Store", "Fruits Corner", "Milk Centre",
                  "Daily Needs"],
    "transport": ["Fuel Station", "Petrol Pump", "Service Station", "Travels", "Auto Stand",
                  "Tours And Travels", "Car Rentals", "Parking", "Tyres", "Motors"],
    "shopping": ["Garments", "Textiles", "Footwear", "Electronics", "Mobiles", "Fashion",
                 "Collections", "Stationery", "Book Depot", "Gift Shop", "Opticals", "Handloom",
                 "Home Decor", "Hardware"],
    "health": ["Medical Stores", "Pharmacy", "Chemist", "Clinic", "Diagnostics", "Hospital",
               "Dental Care", "Eye Care", "Physiotherapy", "Medicals"],
    "entertainment": ["Cinemas", "Multiplex", "Gaming Zone", "Bowling", "Amusement Park", "Club",
                      "Sports Arena", "Turf"],
    "other": ["Academy", "Coaching Centre", "Institute", "Insurance", "Xerox", "Tailors",
              "Laundry", "Salon", "Beauty Parlour"],
}
# Generic names give no hint of their category. They keep evaluation honest:
# no model should be confident about "Sri Balaji Enterprises".
GENERIC = ["Enterprises", "Traders", "Agencies", "Stores", "Associates"]
EMPLOYERS = ["Acme Technologies Pvt Ltd", "Nimbus Softech Pvt Ltd", "Orbit Analytics LLP",
             "Kaveri Infosystems Ltd", "Bluepeak Solutions Pvt Ltd", "Zenith Retail Pvt Ltd"]
PSPS_MERCHANT = ["icici", "hdfcbank", "axisbank", "ybl", "paytm", "okicici"]
PSPS_PERSON = ["okaxis", "okicici", "okhdfcbank", "oksbi", "ybl", "ibl", "axl", "paytm"]

SUBSCRIPTIONS = {  # merchant id -> monthly price options (₹)
    "netflix": [149, 199, 499, 649], "spotify": [59, 119], "youtube_premium": [89, 149],
    "jiohotstar": [149, 299], "amazon_prime": [299], "sonyliv": [199], "zee5": [99],
    "google_play": [130, 210], "microsoft": [489], "linkedin": [1950], "apple_services": [99],
}


def _known(category: str) -> list[dict]:
    return [m for m in rules()["merchants"] if m["category"] == category]


@dataclass
class Account:
    alias: str
    bank: str
    kind: str  # "savings" | "credit_card"
    mask: str
    card_mask: str  # debit card digits for savings, card digits for credit cards
    balance: int = 0
    limit: int = 0
    outstanding: int = 0


@dataclass
class Txn:
    user_id: str
    txn_id: str
    ts: datetime
    amount_paise: int
    direction: str
    category: str
    channel: str
    payee_raw: str | None
    merchant_identity: str
    account: Account
    person: bool = False
    is_self_transfer: bool = False
    is_refund: bool = False
    is_anomaly: bool = False
    recurring_group: str | None = None
    ref_no: str | None = None
    narration: str = ""
    balance_after: int | None = None
    sms: R.Rendered | None = None
    merchant_norm: str = ""
    descriptor: str = ""
    mode: str = "other"


@dataclass
class User:
    uid: str
    persona: str
    rng: random.Random
    name: str
    accounts: list[Account]
    local: dict[str, list[str]] = field(default_factory=dict)
    friends: list[str] = field(default_factory=list)
    txns: list[Txn] = field(default_factory=list)
    counter: int = 0

    @property
    def primary(self) -> Account:
        return self.accounts[0]

    def card(self) -> Account | None:
        return next((a for a in self.accounts if a.kind == "credit_card"), None)

    def second(self) -> Account | None:
        savings = [a for a in self.accounts if a.kind == "savings"]
        return savings[1] if len(savings) > 1 else None


def _ref(rng: random.Random) -> str:
    return str(rng.randrange(4 * 10**11, 7 * 10**11))


def _at(day: date, rng: random.Random, hours: tuple[int, int] = (8, 22)) -> datetime:
    h = rng.randrange(*hours)
    return datetime.combine(day, time(h, rng.randrange(60), rng.randrange(60)), IST)


def _rupees(rng: random.Random, lo: int, hi: int) -> int:
    """A price in paise: round rupees for small amounts, some with paise."""
    value = rng.uniform(lo, hi)
    if rng.random() < 0.7:
        return int(round(value)) * 100
    return int(round(value * 100))


def _person_name(rng: random.Random) -> str:
    return f"{rng.choice(FIRST)} {rng.choice(LAST)}"


def _local_name(rng: random.Random, category: str) -> str:
    words = rng.sample(PREFIX, rng.choice([1, 1, 2]))
    return " ".join(words + [rng.choice(LONG_TAIL[category])])


def _payee_for_known(rng: random.Random, m: dict) -> str:
    alias = rng.choice(m["aliases"])
    roll = rng.random()
    if roll < 0.4:
        return alias.upper()
    if roll < 0.7:
        return alias.replace(" ", "") + "@" + rng.choice(PSPS_MERCHANT)
    return m["name"]


def _payee_for_local(rng: random.Random, name: str) -> str:
    roll = rng.random()
    if roll < 0.55:
        return name.upper()
    if roll < 0.75:
        return f"paytmqr{rng.randrange(10**9, 10**10)}{rng.choice('abcdefgh')}@paytm"
    if roll < 0.9:
        return f"q{rng.randrange(10**8, 10**9)}@ybl"
    return f"bharatpe.{rng.randrange(9 * 10**9, 10**10)}@fbpe"


def _payee_for_person(rng: random.Random, name: str) -> str:
    roll = rng.random()
    if roll < 0.5:
        return name.upper()
    if roll < 0.8:
        first, last = name.lower().split()
        return f"{first}.{last[0]}@{rng.choice(PSPS_PERSON)}" if rng.random() < 0.5 else \
            f"{first}{last}@{rng.choice(PSPS_PERSON)}"
    return f"{rng.randrange(6 * 10**9, 10**10)}@{rng.choice(PSPS_PERSON)}"


def make_user(i: int, seed: int) -> User:
    rng = random.Random(seed * 1000 + i)
    persona = "student" if rng.random() < 0.55 else "professional"
    banks = list(R.BANK_NAMES)
    bank = rng.choice(banks)
    accounts = [Account(f"u{i}_a1", bank, "savings", f"{rng.randrange(1000, 9999)}",
                        f"{rng.randrange(1000, 9999)}",
                        balance=rng.randrange(3_000, 25_000) * 100 if persona == "student"
                        else rng.randrange(20_000, 150_000) * 100)]
    if persona == "professional" and rng.random() < 0.35:
        accounts.append(Account(f"u{i}_a2", rng.choice(banks), "savings",
                                f"{rng.randrange(1000, 9999)}", f"{rng.randrange(1000, 9999)}",
                                balance=rng.randrange(5_000, 60_000) * 100))
    if persona == "professional" and rng.random() < 0.6:
        accounts.append(Account(f"u{i}_cc", rng.choice(["hdfc", "icici", "axis", "sbi"]),
                                "credit_card", "", f"{rng.randrange(1000, 9999)}",
                                limit=rng.choice([50_000, 100_000, 200_000]) * 100))
    user = User(f"u{i:03d}", persona, rng, _person_name(rng), accounts)
    user.local = {c: [_local_name(rng, c) for _ in range(rng.randrange(3, 7))] for c in LONG_TAIL}
    for _ in range(rng.randrange(1, 4)):  # a few shops with generic names, any category
        category = rng.choice(["groceries", "shopping", "other", "health", "food"])
        user.local[category].append(f"{rng.choice(PREFIX)} {rng.choice(GENERIC)}")
    user.friends = [_person_name(rng) for _ in range(rng.randrange(4, 10))]
    return user


class Sim:
    def __init__(self, user: User):
        self.u = user
        self.rng = user.rng
        self.pending_refunds: list[tuple[date, Txn]] = []
        self.scale = 1.0  # day-to-day prices scale with income, set in run()
        self.parent: str | None = None
        self.payees: dict[str, str] = {}

    def payee(self, identity: str, make) -> str:
        """Counterparties keep one spelling (their UPI handle or name); 10% vary."""
        if identity not in self.payees or self.rng.random() < 0.1:
            spelled = make()
            self.payees.setdefault(identity, spelled)
            return spelled
        return self.payees[identity]

    def _fund(self, account: Account, amount: int, day: date) -> bool:
        """A savings debit needs money: students ask a parent, otherwise the bank declines."""
        if account.kind == "credit_card" or account.balance >= amount:
            return True
        if self.u.persona == "student" and self.parent:
            need = amount - account.balance
            top_up = (need // 100 + self.rng.randrange(2_000, 5_000)) * 100
            self._new(_at(day, self.rng, (7, 9)), top_up, "credit", "transfers", "upi",
                      _payee_for_person(self.rng, self.parent), "person:" + self.parent,
                      account, person=True, ref_no=_ref(self.rng))
            return True
        return False

    # ------------------------------------------------------------ emit helpers

    def _new(self, ts: datetime, amount: int, direction: str, category: str, channel: str,
             payee: str | None, identity: str, account: Account, **kw) -> Txn:
        self.u.counter += 1
        t = Txn(self.u.uid, f"{self.u.uid}_{self.u.counter:05d}", ts, amount, direction, category,
                channel, payee, identity, account, **kw)
        if account.kind == "credit_card":
            account.outstanding += amount if direction == "debit" else -amount
        else:
            account.balance += -amount if direction == "debit" else amount
            t.balance_after = account.balance
        self.u.txns.append(t)
        return t

    def spend(self, day: date, category: str, lo: int, hi: int, hours=(8, 22),
              known_share: float = 0.6, card_share: float = 0.0,
              debit_card_share: float = 0.04, merchant: dict | None = None,
              recurring_group: str | None = None, autopay: bool = False,
              amount: int | None = None, anomaly: bool = False) -> Txn | None:
        rng = self.rng
        known = _known(category)
        if merchant is None and known and rng.random() < known_share:
            merchant = rng.choice(known)
        if merchant is not None:
            identity = merchant["id"]
            payee = self.payee(identity, lambda: _payee_for_known(rng, merchant))
        else:
            identity = rng.choice(self.u.local[category])
            payee = self.payee(identity, lambda: _payee_for_local(rng, identity))
        cc = self.u.card()
        roll = rng.random()
        if cc is not None and roll < card_share:
            account, use_card = cc, True
        elif not autopay and roll < card_share + debit_card_share:
            account, use_card = self.u.primary, True  # debit card on the savings account
        else:
            account, use_card = self.u.primary, False
        channel = "card" if use_card else ("upi_autopay" if autopay else "upi")
        if channel == "card" and "@" in payee:
            payee = identity.upper() if merchant is None else merchant["aliases"][0].upper()
        if amount is None:
            amount = _rupees(rng, max(1, int(lo * self.scale)), max(2, int(hi * self.scale)))
        if not self._fund(account, amount, day):
            return None
        t = self._new(_at(day, rng, hours), amount, "debit", category, channel, payee, identity,
                      account, recurring_group=recurring_group, is_anomaly=anomaly,
                      ref_no=None if channel == "card" else _ref(rng))
        if category == "shopping" and rng.random() < 0.08 and not anomaly:
            self.pending_refunds.append((day + timedelta(days=rng.randrange(3, 11)), t))
        return t

    def p2p_out(self, day: date, name: str, lo: int, hi: int, category: str = "transfers",
                recurring_group: str | None = None, amount: int | None = None) -> Txn | None:
        rng = self.rng
        if amount is None:
            amount = _rupees(rng, max(1, int(lo * self.scale)), max(2, int(hi * self.scale)))
        if not self._fund(self.u.primary, amount, day):
            return None
        return self._new(_at(day, rng), amount, "debit", category, "upi",
                         self.payee("person:" + name, lambda: _payee_for_person(rng, name)),
                         "person:" + name, self.u.primary,
                         person=True, recurring_group=recurring_group, ref_no=_ref(rng))

    def p2p_in(self, day: date, name: str, lo: int, hi: int, category: str = "transfers") -> Txn:
        rng = self.rng
        return self._new(_at(day, rng), _rupees(rng, lo, hi), "credit", category, "upi",
                         self.payee("person:" + name, lambda: _payee_for_person(rng, name)),
                         "person:" + name, self.u.primary, person=True, ref_no=_ref(rng))

    def salary(self, day: date, employer: str, amount: int) -> Txn:
        rng = self.rng
        month = R.MON[day.month - 1].upper()
        return self._new(_at(day, rng, (9, 12)), amount, "credit", "income", "neft", employer.upper(),
                         employer, self.u.primary, recurring_group=f"{self.u.uid}:salary",
                         ref_no=f"CITIN5{rng.randrange(10**15, 10**16)}",
                         narration=f"SALARY {month} {day.year}")

    def refund(self, day: date, original: Txn) -> Txn:
        rng = self.rng
        amount = original.amount_paise if rng.random() < 0.7 else original.amount_paise // 2
        payee = original.payee_raw if "@" not in (original.payee_raw or "") else \
            original.merchant_identity.upper()
        account = original.account if original.account.kind != "credit_card" else self.u.primary
        return self._new(_at(day, rng), amount, "credit", original.category, "refund", payee,
                         original.merchant_identity, account, is_refund=True, ref_no=_ref(rng))

    def self_transfer(self, day: date, amount: int) -> None:
        second = self.u.second()
        if second is None:
            return
        if self.u.primary.balance < amount + 200_000:
            return
        ts = _at(day, self.rng)
        ref = _ref(self.rng)
        me = self.u.name
        out = self._new(ts, amount, "debit", "transfers", "upi", _payee_for_person(self.rng, me),
                        "self", self.u.primary, person=True, is_self_transfer=True, ref_no=ref)
        back = self._new(ts + timedelta(seconds=self.rng.randrange(5, 90)), amount, "credit",
                         "transfers", "upi", _payee_for_person(self.rng, me), "self", second,
                         person=True, is_self_transfer=True, ref_no=ref)
        out.recurring_group = back.recurring_group = None

    def card_bill(self, day: date) -> None:
        cc = self.u.card()
        if cc is None or cc.outstanding <= 0:
            return
        amount = min(cc.outstanding, max(0, self.u.primary.balance - 100_000))
        if amount <= 0:
            return
        payee = self.rng.choice(["CRED CLUB", "cred.club@axisb", "CRED"])
        self._new(_at(day, self.rng), amount, "debit", "transfers", "upi", payee, "cred",
                  self.u.primary, is_self_transfer=True, ref_no=_ref(self.rng))
        self._new(_at(day, self.rng, (22, 23)), amount, "credit", "transfers", "card_payment",
                  None, "cred", cc, is_self_transfer=True)

    # ------------------------------------------------------------ the months

    def run(self) -> None:
        u, rng = self.u, self.rng
        student = u.persona == "student"
        employer = rng.choice(EMPLOYERS)
        salary = rng.randrange(35_000, 120_000, 500) * 100
        allowance = rng.randrange(10_000, 22_000, 500) * 100
        allowance_day = rng.randrange(1, 4)
        parent = _person_name(rng)
        self.parent = parent if student else None
        self.scale = (allowance / 1_600_000) if student else (salary / 8_000_000)
        self.scale = min(1.4, max(0.6, self.scale))
        landlord = _person_name(rng)
        rent = min(rng.randrange(8_000, 25_000, 500) * 100, int(salary * 0.35) // 50_000 * 50_000)
        subs = rng.sample(sorted(SUBSCRIPTIONS), k=rng.randrange(1, 3) if student
                          else rng.randrange(2, 5))
        sub_price = {s: rng.choice(SUBSCRIPTIONS[s]) * 100 for s in subs}
        sub_day = {s: rng.randrange(1, 28) for s in subs}
        telco = rng.choice([m for m in _known("utilities") if m["id"] in ("jio", "airtel", "vi")])
        recharge = rng.choice([199, 239, 299, 349]) * 100
        recharge_day = START + timedelta(days=rng.randrange(0, 20))
        power = rng.choice([m for m in _known("utilities") if m["id"] in (
            "bescom", "tata_power", "msedcl", "adani_electricity", "tangedco", "tgspdcl", "bses")])
        power_base = rng.randrange(700, 2_500)
        broadband = rng.choice([m for m in _known("utilities") if m["id"] in (
            "act_fibernet", "hathway", "excitel", "airtel", "jio")])
        broadband_price = rng.choice([599, 699, 799, 999, 1_199]) * 100
        sip = rng.choice([m for m in _known("other") if m["id"] in ("zerodha", "groww", "upstox")])
        sip_amount = rng.randrange(1_000, 10_000, 500) * 100
        gym = rng.random() < 0.3 and not student
        anomaly_days = sorted(rng.sample(range((END - START).days), k=rng.randrange(2, 5)))

        day = START
        while day <= END:
            dom, dow = day.day, day.weekday()
            weekend = dow >= 5
            if not student and dom == 1:
                self.salary(day, employer, salary + rng.randrange(0, 2) * 100)
            if student and dom == allowance_day:
                self.p2p_in(day, parent, allowance // 100, allowance // 100)
            if not student and dom == 3:
                self.p2p_out(day, landlord, 0, 0, amount=rent,
                             recurring_group=f"{u.uid}:rent")
            for s in subs:
                if dom == sub_day[s]:
                    m = next(x for x in rules()["merchants"] if x["id"] == s)
                    self.spend(day, "subscriptions", 0, 0, merchant=m, amount=sub_price[s],
                               recurring_group=f"{u.uid}:{s}", autopay=rng.random() < 0.6,
                               card_share=0.5, hours=(0, 7))
            if (day - recharge_day).days >= 0 and (day - recharge_day).days % 28 == 0:
                self.spend(day, "utilities", 0, 0, merchant=telco, amount=recharge,
                           recurring_group=f"{u.uid}:{telco['id']}-recharge")
            if not student:
                if dom == 12:
                    amount = int(power_base * rng.uniform(0.75, 1.3)) * 100
                    self.spend(day, "utilities", 0, 0, merchant=power, amount=amount,
                               recurring_group=f"{u.uid}:{power['id']}")
                if dom == 7:
                    self.spend(day, "utilities", 0, 0, merchant=broadband,
                               amount=broadband_price, recurring_group=f"{u.uid}:broadband",
                               autopay=True)
                if dom == 10:
                    self.spend(day, "other", 0, 0, merchant=sip, amount=sip_amount,
                               recurring_group=f"{u.uid}:sip", autopay=True)
                if gym and dom == 15:
                    cult = next(x for x in rules()["merchants"] if x["id"] == "cultfit")
                    self.spend(day, "health", 0, 0, merchant=cult, amount=149_900,
                               recurring_group=f"{u.uid}:cultfit", card_share=0.7)
                if dom == 18:
                    self.card_bill(day)
                if dom == 25 and rng.random() < 0.5:
                    self.self_transfer(day, rng.randrange(2_000, 20_000, 500) * 100)

            # day-to-day
            if student:
                if rng.random() < 0.65:
                    self.spend(day, "food", 10, 80, known_share=0.0, hours=(9, 20))
                if rng.random() < (0.45 if weekend else 0.3):
                    self.spend(day, "food", 140, 450, known_share=0.85, hours=(12, 23))
                if rng.random() < 0.45:
                    self.spend(day, "transport", 30, 220, known_share=0.7)
                if rng.random() < 0.08:
                    self.spend(day, "groceries", 80, 900, known_share=0.6, debit_card_share=0.15)
                if rng.random() < 0.05:
                    self.spend(day, "shopping", 250, 2_500, known_share=0.7, debit_card_share=0.25)
                if rng.random() < 0.04:
                    self.spend(day, "entertainment", 150, 600, known_share=0.7)
                if rng.random() < 0.025:
                    self.spend(day, "health", 60, 700, known_share=0.4)
                if rng.random() < 0.02:
                    self.spend(day, "other", 50, 999, known_share=0.3)
                if rng.random() < 0.25:
                    self.p2p_out(day, rng.choice(u.friends), 40, 500)
                if rng.random() < 0.15:
                    self.p2p_in(day, rng.choice(u.friends), 40, 500)
            else:
                if not weekend and rng.random() < 0.6:
                    self.spend(day, "food", 40, 220, known_share=0.0, hours=(9, 18))
                if rng.random() < (0.55 if weekend else 0.4):
                    self.spend(day, "food", 180, 900, known_share=0.85, hours=(12, 23),
                               card_share=0.3)
                if rng.random() < 0.55:
                    self.spend(day, "transport", 80, 600, known_share=0.75, card_share=0.2)
                if rng.random() < 0.07:
                    self.spend(day, "transport", 500, 3_000, known_share=0.8, card_share=0.6)
                if rng.random() < 0.18:
                    self.spend(day, "groceries", 250, 2_200, known_share=0.7, card_share=0.3)
                if rng.random() < 0.1:
                    self.spend(day, "shopping", 400, 6_000, known_share=0.7, card_share=0.6)
                if rng.random() < 0.06:
                    self.spend(day, "entertainment", 250, 2_500, known_share=0.7,
                               card_share=0.4)
                if rng.random() < 0.05:
                    self.spend(day, "health", 150, 2_500, known_share=0.5, card_share=0.3)
                if rng.random() < 0.03:
                    self.spend(day, "other", 200, 3_000, known_share=0.3)
                if rng.random() < 0.18:
                    self.p2p_out(day, rng.choice(u.friends), 150, 3_000)
                if rng.random() < 0.08:
                    self.p2p_in(day, rng.choice(u.friends), 150, 2_000)

            if (day - START).days in anomaly_days:
                category = rng.choice(["food", "shopping", "transport", "entertainment",
                                       "groceries", "health"])
                typical = {"food": 300, "shopping": 1_500, "transport": 250,
                           "entertainment": 500, "groceries": 700, "health": 500}[category]
                amount = int(typical * self.scale * rng.uniform(6, 15)) * 100
                self.spend(day, category, 0, 0, amount=amount, anomaly=True, known_share=0.7)

            for when, original in list(self.pending_refunds):
                if when == day:
                    self.refund(day, original)
                    self.pending_refunds.remove((when, original))
            day += timedelta(days=1)
        u.txns.sort(key=lambda t: t.ts)


# ---------------------------------------------------------------- SMS and features


def render(t: Txn, rng: random.Random) -> R.Rendered:
    a = t.account
    if a.kind == "credit_card":
        if t.direction == "credit":
            return R.card_payment_received(rng, a.bank, a.card_mask, t.amount_paise, t.ts)
        return R.credit_card(rng, a.bank, a.card_mask, t.amount_paise, t.payee_raw, t.ts,
                             a.limit - a.outstanding)
    if t.channel == "neft":
        return R.neft_credit(rng, a.bank, a.mask, t.amount_paise, t.payee_raw, t.ref_no,
                             t.narration, t.ts, t.balance_after)
    if t.channel == "refund":
        return R.refund_credit(rng, a.bank, a.mask, t.amount_paise, t.payee_raw, t.ref_no, t.ts)
    if t.channel == "upi_autopay":
        return R.upi_autopay(rng, a.bank, a.mask, t.amount_paise, t.payee_raw, t.ref_no, t.ts)
    if t.channel == "card":
        return R.debit_card(rng, a.bank, a.card_mask, t.amount_paise, t.payee_raw, t.ts,
                            t.balance_after)
    if t.direction == "debit":
        return R.upi_debit(rng, a.bank, a.mask, t.amount_paise, t.payee_raw, t.ref_no, t.ts,
                           t.person)
    return R.upi_credit(rng, a.bank, a.mask, t.amount_paise, t.payee_raw, t.ref_no, t.ts,
                        t.balance_after, t.person)


def phone_features(t: Txn) -> None:
    """What the phone would send for this transaction: merchant key, descriptor, mode."""
    exp = t.sms.expected
    name = resolve(exp.get("merchant_raw"), SALT, p2a=exp.get("p2a", False),
                   p2m=exp.get("p2m", False))
    extra = []
    if exp.get("card"):
        extra.append(f"{exp['card']}_card")
    if exp.get("p2m"):
        extra.append("p2m")
    if exp.get("p2a"):
        extra.append("p2a")
    if name.kind == "qr":
        extra.append("qr")
    t.merchant_norm = name.key
    t.descriptor = descriptor(exp.get("hints", []), extra)
    t.mode = exp["mode"]
    if exp.get("is_card_bill") or is_card_bill_name(exp.get("merchant_raw") or ""):
        t.is_self_transfer = True


def generate(n_users: int = 60, seed: int = 7) -> list[User]:
    users = []
    for i in range(n_users):
        user = make_user(i, seed)
        Sim(user).run()
        render_rng = random.Random(seed * 7919 + i)
        for t in user.txns:
            t.sms = render(t, render_rng)
            phone_features(t)
        users.append(user)
    return users


def noise_messages(users: list[User], per_user: int = 6, seed: int = 11) -> list[tuple[User, R.Rendered, datetime]]:
    rng = random.Random(seed)
    out = []
    for u in users:
        a = u.primary
        for _ in range(per_user):
            day = START + timedelta(days=rng.randrange((END - START).days))
            ts = _at(day, rng)
            roll = rng.random()
            if roll < 0.55:
                msg = R.noise(rng, a.bank, a.mask, a.card_mask, ts)
            elif roll < 0.7:
                msg = R.promo(rng, a.bank)
            elif roll < 0.85:
                msg = R.balance_only(rng, a.bank, a.mask, rng.randrange(1_000, 90_000) * 100, ts)
            else:
                msg = R.personal(rng)
            out.append((u, msg, ts))
    return out
