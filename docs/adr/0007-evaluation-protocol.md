# ADR-007: Evaluation protocol

Status: Accepted; the real test set is still to be collected
Date: 2026-09-30 · Deciders: the team and the project guide

## Context

Training and testing only on synthetic data gives inflated, circular scores:
the same people wrote the generator and the parser.

## Decision

- **Synthetic** data (60 users, March to August 2026) trains the models and
  catches regressions. Every report says so in a banner.
- **Real** data: each member exports their own messages with the debug-only
  masked export, labels them, and the team keeps a real test set that is never
  used for tuning (`ml/data/README.md`). Only these results are presented as
  findings.
- Classifier: 5-fold cross-validation grouped by true merchant, on the rows the
  model actually sees (rows the phone's rules resolve are excluded). Report
  macro-F1, accuracy, coverage, accuracy when answering and accuracy at the
  baseline's coverage, against a lookup-plus-keywords baseline.
- Recurring: precision and recall against the generator's subscriptions and
  bills; baseline is an exact monthly match.
- Anomalies: precision and recall on injected outliers; baselines are 3x the
  category mean and an Isolation Forest.
- Forecast: month-end MAE at cut-off days 8, 15 and 22, for run-rate, EWMA,
  linear trend and automatic per-user selection.

`make eval` writes all of this to `ml/reports/latest.md` and `latest.json`.

## Consequences

- Costs labelling time, and each member must consent to using their messages.
- The current report has no real-data section yet; collecting it is the top
  ML item in `docs/tech-debt.md`.
