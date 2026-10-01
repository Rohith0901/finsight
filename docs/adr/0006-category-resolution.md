# ADR-006: Category resolution order and correction loop

Status: Accepted (revised 2026-10-01)
Date: 2026-09-30 · Deciders: the team

## Context

The pitch promised "self-learning categorisation" without saying how.

## Decision (as built)

Every transaction is resolved in this order, on the phone
(`lib/ingestion/pipeline.dart`), and the first match wins:

1. **Self transfer.** Credit-card bill payments, and a debit and a credit of
   the same amount on two of your accounts within 30 minutes (naming the same
   person, or no one), become Transfers and are excluded from spending.
2. **Your override** for this merchant key (or for the raw UPI handle, for
   anonymous QR payments, so one correction labels a tea stall's QR for good).
3. **Rules.** People are Transfers; known brands (`shared/merchants.json`, 124
   merchants) map to their category; credits hinted as salary, interest or
   cashback are Income.
4. **The model** (`POST /v1/classify`), only for rows still pending. It abstains
   below its threshold (0.3 for named merchants; stricter for anonymous
   handles), and the row shows as Unknown until you pick a category.

A correction writes the override at once, recategorises that merchant's other
transactions, and is logged in `corrections` for the masked export. Retraining
happens offline on exported corrections.

## Why the revision

The original order (override, exact match, model, Unknown) had no step for self
transfers and people. Without them, card bills double-count spending and
payments to friends land in "Shopping".

## Options considered

| Option | For | Against |
| --- | --- | --- |
| **Overrides plus offline retraining (chosen)** | Instant, visible, no server state | Learning across users only at retraining |
| Online learning on the server | Learns continuously | Needs stored per-user data (ADR-001) |
| Per-user models | Personal | Too little data per user |

## Consequences

- Describe it as "instant personalisation plus periodic retraining". Measure
  it by the share of corrected merchants that stay correct.
- People are detected by name shape (2 to 4 alphabetic words, or one long word
  on a personal UPI app, no business words), so some small shops that use a
  personal UPI handle are filed as Transfers until corrected.
