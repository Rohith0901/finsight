# ADR-003: Model inference runs in FastAPI

Status: Accepted
Date: 2026-09-30 · Deciders: the team

## Context

The classifier, recurring detection, anomaly detection and forecast are Python
(scikit-learn and numpy).

## Decision

Serve them from the FastAPI backend under `/v1`, versioned and reported by
`GET /v1/model-info`. The classifier is exported to portable JSON (vocabulary,
IDF weights, base64 float32 coefficients, temperature, thresholds) and run with
numpy, so the service does not need scikit-learn at runtime. A parity test
(`ml/tests/test_export_parity.py`) checks the numpy path against scikit-learn
to 1e-5.

## Options considered

| Option | For | Against |
| --- | --- | --- |
| **Server-side inference (chosen)** | Notebook to app in one step; models change without an app release | Predictions need the laptop |
| On-device export | Offline | Conversion step and Dart feature code |
| Hybrid | Rules on the phone, models on the server | (this is what we have; see ADR-006) |

## Consequences

- The phone does what doesn't need a model (parsing, known merchants, people,
  salary) and the server does the rest.
- The JSON artifact (about 0.4 MB) is small enough to ship inside the app later
  if offline categorisation is wanted; the features are TF-IDF on word 1-2 grams
  and character 3-5 grams, which are straightforward to port.
