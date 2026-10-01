from datetime import date, timedelta

from conftest import daily, monthly, txn

from finsight_api.ml.anomaly import detect_anomalies
from finsight_api.ml.recurring import detect_recurring, due_dates


def test_detects_monthly_subscription():
    items = detect_recurring(monthly(date(2026, 4, 5), 5, 649, "netflix"), date(2026, 9, 1))
    [n] = items
    assert (n.merchant_norm, n.period, n.kind) == ("netflix", "monthly", "subscription")
    assert n.next_due == date(2026, 9, 5)
    assert n.occurrences == 5


def test_detects_28_day_recharge_and_variable_bill():
    recharge = [txn(date(2026, 3, 2) + timedelta(days=28 * k), 299, "jio", "utilities")
                for k in range(6)]
    power = [txn(date(2026, 3, 12).replace(month=3 + k), a, "bescom", "utilities")
             for k, a in enumerate([900, 1200, 1500, 1100, 1000, 1300])]
    by = {i.merchant_norm: i for i in detect_recurring(recharge + power, date(2026, 8, 31))}
    assert by["jio"].period == "28-day"
    assert by["bescom"].kind == "bill"


def test_finds_membership_inside_busy_merchant():
    orders = daily(date(2026, 4, 1), date(2026, 8, 30), 350, "swiggy")
    membership = monthly(date(2026, 4, 10), 5, 299, "swiggy", "food")
    [item] = detect_recurring(orders + membership, date(2026, 8, 31))
    assert item.median_amount_paise == 29900


def test_two_payments_are_not_a_rhythm():
    pair = [txn(date(2026, 4, 1), 500, "dmart"), txn(date(2026, 7, 1), 510, "dmart")]
    assert detect_recurring(pair, date(2026, 8, 1)) == []


def test_stopped_subscription_is_dropped():
    old = monthly(date(2026, 1, 5), 3, 199, "zee5")  # last paid 5 March
    assert detect_recurring(old, date(2026, 8, 1)) == []


def test_due_dates_with_grace():
    assert due_dates(date(2026, 9, 18), "monthly", date(2026, 9, 20), date(2026, 9, 30), 4) == [
        date(2026, 9, 20)]  # two days late still counts
    assert due_dates(date(2026, 9, 1), "monthly", date(2026, 9, 20), date(2026, 9, 30), 4) == []
    assert len(due_dates(date(2026, 9, 21), "weekly", date(2026, 9, 20), date(2026, 9, 30), 2)) == 2


def test_anomaly_flags_big_payment_but_not_dinners():
    # Bimodal food: ₹40 teas and ₹350 dinners are both normal.
    teas = daily(date(2026, 6, 1), date(2026, 9, 20), 40, "tea stall")
    dinners = [txn(date(2026, 6, 1) + timedelta(days=3 * k), 350, "zomato") for k in range(35)]
    big = txn(date(2026, 9, 18), 4500, "zomato")
    flagged = detect_anomalies(teas + dinners + [big], date(2026, 9, 20))
    assert [a.id for a in flagged] == [big.id]
    assert "usually up to" in flagged[0].reason


def test_anomaly_needs_history():
    few = [txn(date(2026, 9, d), 100) for d in range(1, 6)] + [txn(date(2026, 9, 10), 9000)]
    assert detect_anomalies(few, date(2026, 9, 20)) == []
