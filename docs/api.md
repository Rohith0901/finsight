# FinSight API reference (v1)

The backend is stateless (ADR-001): every request carries the data it needs,
and nothing is stored. The live schema is at `https://<host>:8443/docs` while
the server runs; this page explains the parts the schema doesn't.

## Basics

| | |
| --- | --- |
| Base URL | `https://<laptop IP>:8443` (self-signed certificate; the app pins its SHA-256 fingerprint) |
| Auth | `Authorization: Bearer <FINSIGHT_API_TOKEN>` on every `/v1` call. `/healthz` is open. |
| Body | JSON, at most 5 MB and 5,000 transactions per request. Unknown fields are rejected (422). |
| Money | Integers in **paise** (`48500` = ₹485). Never floats. |
| Times | `ts` is an ISO 8601 timestamp in UTC (`2026-09-12T04:30:00Z`). `as_of` is a date (`2026-09-20`) in the user's local calendar; it defaults to today. |
| Logging | The access log records method, path, status and duration. Bodies are never logged. |

### The transaction object

This is the only shape of user data the server ever sees. The phone builds it
in `Txn.toApi()` (`app/lib/data/models.dart`).

| Field | Type | Notes |
| --- | --- | --- |
| `id` | string, 1-64 | The phone's row id; echoed back in results |
| `ts` | datetime | UTC |
| `amount_paise` | int, ≤ 10¹² | Always positive |
| `direction` | `debit` \| `credit` | |
| `merchant_norm` | string, ≤ 120 | Normalised key: `swiggy`, `sri balaji sweets`, or `person:<10 hex>` for people. Never a raw SMS name. |
| `category` | string \| null | One of `shared/categories.json`, or `unknown` |
| `account_alias` | string \| null | `acct_1`, `acct_2`… never an account number |
| `mode` | enum | `upi`, `card`, `netbanking`, `atm`, `imps`, `neft`, `rtgs`, `wallet`, `cash`, `other` |
| `is_self_transfer` | bool | Excluded from spending |
| `is_refund` | bool | Credits that reduce spending in their category |

### Errors

Every error has the same body. Validation messages name the field, never the
value sent.

```json
{"error": {"code": "validation_error", "message": "transactions.0.amount_paise: Input should be less than or equal to 1000000000000"}}
```

| Status | `code` | When |
| --- | --- | --- |
| 401 | `unauthorized` | Missing or wrong token |
| 413 | `payload_too_large` | Body over 5 MB |
| 422 | `validation_error` | Schema violation, unknown field, too many rows |
| 503 | `model_unavailable` | No classifier artifact on the server (`make train`) |

## Endpoints

| Method and path | Request | Use |
| --- | --- | --- |
| `GET /healthz` | | Liveness; `{"status": "ok", "api_version": "v1"}` |
| `GET /v1/model-info` | | Classifier version, metrics, thresholds; algorithm settings; enabled LLM providers |
| `POST /v1/classify` | `items[]` (≤ 500) | Categories for rows the phone's rules couldn't resolve |
| `POST /v1/insights` | window + balance + savings target | **What the app calls.** Recurring, anomalies, forecast and safe-to-spend in one round trip |
| `POST /v1/recurring` | window | Subscriptions and bills |
| `POST /v1/anomalies` | window | Unusually large payments |
| `POST /v1/forecast` | window, optional `recurring` | Month-end projection |
| `POST /v1/safe-to-spend` | balance, savings target, optional `recurring` and `transactions` | Today's safe amount |
| `POST /v1/whatif` | window + `changes[]` (≤ 20) | Effect of cutting a category or cancelling a subscription |
| `POST /v1/chat` | window + `question` (≤ 500 chars) + `provider` | Grounded answer with the facts used |

A "window" is `{"transactions": [...], "as_of": "YYYY-MM-DD"}`. The app sends
the last 120 days.

### POST /v1/classify

```json
{"items": [{"id": "7", "merchant_norm": "sri balaji sweets", "descriptor": "",
            "mode": "upi", "direction": "debit", "amount_paise": 6000}]}
```

`descriptor` carries non-identifying hint tokens from the SMS (`autopay`,
`p2m`, `credit_card`, `qr`…). Response:

```json
{"model_version": "v1", "threshold": 0.3,
 "items": [{"id": "7", "category": "food", "confidence": 0.9875, "abstained": false,
            "candidates": [{"category": "food", "probability": 0.9875},
                           {"category": "other", "probability": 0.009},
                           {"category": "transport", "probability": 0.0025}]}]}
```

When `abstained` is true the phone stores `unknown`. Anonymous UPI handles use
a stricter threshold than named merchants (see `/v1/model-info`).

### POST /v1/insights

Request: a window plus `balance_paise` (optional; omit it and
`safe_to_spend` is `null`) and `savings_target_paise` (default 0).

Response: `{"as_of", "recurring", "anomalies", "forecast", "safe_to_spend"}`,
each the same object as its own endpoint returns.

**Forecast.** `projected_month_end = spent_so_far + projected_variable_rest +
recurring_due`, where `spent_so_far` includes today, `projected_variable_rest =
max(0, V − today's variable spend) + V × days after today`, `V` is the
day-to-day rate (EWMA by default, `chosen_model` says which), and
`recurring_due` is recurring payments due from today to month end that haven't
been paid. `error_band_paise` comes from backtesting the same method on the
user's own history.

**Recurring.** Payments to the same merchant at a regular interval (weekly,
28-day, monthly, quarterly, yearly) with steady amounts; at least 3 payments
(5 for weekly). Each item has `next_due`, `monthly_cost_paise` and the
`txn_ids` it was built from.

**Anomalies.** A payment is flagged when its robust z-score on log amounts
within its category is above 2.5 and it is at least 2× the category's 90th
percentile, with at least 8 earlier payments in the category and an amount of
at least ₹300. `reason` is a ready-to-show sentence.

**Safe-to-spend.**

```
safe_total = max(0, balance − recurring due before month end − savings target)
safe_daily = safe_total ÷ days left (including today)
```

`status` is `no_room` when `safe_total` is 0, `at_risk` when the forecast's
remaining day-to-day spending (`projected_variable_paise`) is more than
`safe_total` (the gap is `projected_shortfall_paise`), and `on_track`
otherwise. The projection needs `transactions`; without them both fields are
`null`.
Expected income before month end is not counted, so the number is
conservative.

Example (`/v1/safe-to-spend` with ₹45,000 balance and a ₹5,000 target on
20 September):

```json
{"as_of": "2026-09-20", "days_left": 11, "balance_paise": 4500000,
 "recurring_due_paise": 0, "savings_target_paise": 500000,
 "safe_total_paise": 4000000, "safe_daily_paise": 363636,
 "projected_variable_paise": null, "projected_shortfall_paise": null,
 "status": "on_track",
 "formula": "safe_daily = max(0, balance - recurring due - savings target) / days left"}
```

### POST /v1/whatif

```json
{"transactions": [...], "as_of": "2026-09-20", "balance_paise": 4500000,
 "changes": [{"kind": "category", "category": "food", "percent_change": -20},
             {"kind": "cancel_recurring", "merchant_norm": "netflix"}]}
```

Returns `baseline` and `scenario` (each with the projected month end,
day-to-day rate and safe daily amount), `saving_this_month_paise`,
`saving_per_month_paise` and plain-language `notes` (for example, when a
subscription to cancel wasn't found).

### POST /v1/chat

```json
{"transactions": [...], "as_of": "2026-09-20",
 "question": "How much did I spend on food this month?",
 "balance_paise": 4500000, "provider": "auto"}
```

`provider` is `auto` (server default), `none` (templates only), `ollama` or
`gemini`. Response:

```json
{"answer": "You've spent ₹5,700 on Food this month, 34% of your ₹16,600 total.",
 "intent": "category_spend",
 "facts": [{"label": "Food", "value": "₹5,700"}, {"label": "All spending", "value": "₹16,600"}],
 "provider_used": "none", "verified": true, "fallback_used": false}
```

How an answer is made (ADR-005): a recognised question is answered from a
template; anything else goes to the model with tools that compute the
numbers. Every number in the model's answer must appear in the tool results,
or the templated answer is returned with `fallback_used: true`. Cloud
providers only get aggregate tools.

Recognised questions: can I afford X, why did I overspend, where did I spend
most, how much did I spend on a category, how much can I spend today,
subscriptions and bills, unusual payments, month-end forecast, comparison with
last month.

## Versioning

Breaking changes get a new prefix (`/v2`). Adding optional request fields or
new response fields is not breaking; the app ignores fields it doesn't know.
`/v1/model-info` reports the classifier version so a retrain is visible.
