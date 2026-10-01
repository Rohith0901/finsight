from datetime import date

from conftest import daily, monthly, txn

from finsight_api.engine.calendar import add_months, days_left_including
from finsight_api.engine.forecast import compute_forecast
from finsight_api.engine.safe_to_spend import compute_safe_to_spend
from finsight_api.engine.spend import spend_delta
from finsight_api.engine.whatif import compute_what_if
from finsight_api.ml.money_text import group_indian, rupees
from finsight_api.ml.recurring import detect_recurring
from finsight_api.schemas import CancelRecurring, CategoryChange, RecurringIn


def test_calendar():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2026, 11, 15), 3) == date(2027, 2, 15)
    assert days_left_including(date(2026, 9, 30)) == 1
    assert days_left_including(date(2026, 9, 1)) == 30


def test_indian_grouping_and_rounding():
    assert group_indian(1234567) == "12,34,567"
    assert group_indian(999) == "999"
    assert rupees(48550) == "₹486"  # half rounds up
    assert rupees(12345678, decimals=True) == "₹1,23,456.78"


def test_spend_rules():
    d = date(2026, 9, 10)
    assert spend_delta(txn(d, 100)) == 10000
    assert spend_delta(txn(d, 100, is_self_transfer=True)) == 0
    assert spend_delta(txn(d, 40, direction="credit", is_refund=True)) == -4000
    assert spend_delta(txn(d, 5000, direction="credit", category="income")) == 0


def test_forecast_steady_spender():
    # ₹300 a day since July; on 20 Sep the rest of the month should be about ₹300 x 11.
    txns = daily(date(2026, 7, 1), date(2026, 9, 19), 300)
    f = compute_forecast(txns, date(2026, 9, 20), [])
    assert f.spent_so_far_paise == 300 * 19 * 100
    assert f.days_left == 11
    assert f.chosen_model == "ewma"
    assert abs(f.variable_daily_paise - 30000) <= 100
    assert abs(f.projected_month_end_paise - 300 * 30 * 100) <= 1500
    assert all(v is not None for v in f.backtest_mae_paise.values())


def test_forecast_counts_a_recurring_payment_made_today_once():
    txns = daily(date(2026, 7, 1), date(2026, 9, 19), 200)
    txns += monthly(date(2026, 6, 20), 4, 649, "netflix")  # last one on 20 Sep (today)
    rec = detect_recurring(txns, date(2026, 9, 20))
    f = compute_forecast(txns, date(2026, 9, 20), rec)
    assert f.recurring_due_paise == 0  # already paid today, next due in October
    assert f.spent_so_far_paise == (200 * 19 + 649) * 100


def test_forecast_with_no_history_uses_run_rate():
    f = compute_forecast([txn(date(2026, 9, 3), 500)], date(2026, 9, 5), [])
    assert f.chosen_model == "run_rate"


def test_safe_to_spend_formula():
    rec = [RecurringIn(merchant_norm="netflix", period="monthly", median_amount_paise=64900,
                       next_due=date(2026, 9, 25))]
    s = compute_safe_to_spend(date(2026, 9, 21), 1_000_000, 200_000, rec)
    # (10,000 - 649 - 2,000) / 10 days
    assert s.days_left == 10
    assert s.recurring_due_paise == 64900
    assert s.safe_total_paise == 1_000_000 - 64900 - 200_000
    assert s.safe_daily_paise == (1_000_000 - 64900 - 200_000) // 10
    assert s.status == "on_track"


def test_safe_to_spend_no_room_and_at_risk():
    assert compute_safe_to_spend(date(2026, 9, 21), 10_000, 50_000, []).status == "no_room"
    txns = daily(date(2026, 7, 1), date(2026, 9, 20), 1000)
    s = compute_safe_to_spend(date(2026, 9, 21), 300_000, 0, [], txns)
    assert s.status == "at_risk"
    assert s.projected_shortfall_paise > 0


def test_what_if_cut_and_cancel():
    txns = daily(date(2026, 7, 1), date(2026, 9, 19), 300, "swiggy", "food")
    txns += daily(date(2026, 7, 1), date(2026, 9, 19), 100, "uber", "transport")
    txns += monthly(date(2026, 6, 25), 3, 649, "netflix")
    rec = detect_recurring(txns, date(2026, 9, 20))
    r = compute_what_if(txns, date(2026, 9, 20), rec,
                        [CategoryChange(category="food", percent_change=-50),
                         CancelRecurring(kind="cancel_recurring", merchant_norm="netflix")],
                        balance_paise=2_000_000, savings_target_paise=0)
    assert r.scenario.recurring_due_paise == 0
    assert r.baseline.recurring_due_paise == 64900
    # food is 75% of day-to-day spend, so a 50% cut lowers the daily rate by 37.5%
    assert abs(r.scenario.variable_daily_paise - r.baseline.variable_daily_paise * 0.625) < 200
    assert r.saving_this_month_paise > 0
    assert r.scenario.safe_daily_paise > r.baseline.safe_daily_paise
