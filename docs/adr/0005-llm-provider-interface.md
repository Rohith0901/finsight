# ADR-005: LLM behind a provider interface

Status: Accepted
Date: 2026-09-30 · Deciders: the team

## Context

Chat needs an LLM, but financial data should not reach third parties by
default, and the budget is ₹0 to ₹1,000.

## Decision

One `Provider` interface (`backend/finsight_api/llm/base.py`) with three
implementations: `none` (templates only), `ollama` (local, default model
`qwen2.5:3b`) and `gemini` (optional, `generateContent`).

The assistant never computes numbers itself:

1. Common questions are matched to an intent and answered from a template
   filled with tool results.
2. Otherwise the model runs a short tool loop. Tools return computed facts.
   Cloud providers get aggregate tools only (totals, forecast, safe-to-spend);
   the local model also gets detail tools (individual transactions).
3. A verifier checks that every number in the answer appears in the tool
   results. If not, the templated answer is returned and `verified` is false.

The response always includes the facts used, the provider and whether a
fallback happened, so the app can show where an answer came from.

## Options considered

| Option | For | Against |
| --- | --- | --- |
| **Pluggable, local default (chosen)** | Keeps the privacy claim, free | Small models need guard rails |
| Gemini only | Better wording | Free-tier terms allow human review and product use |
| Local only | Simplest | Quality tied to the laptop |

## Consequences

- Chat works with no model at all (templates), which is also the demo fallback.
- If Gemini is enabled, use a paid key and keep it to aggregates.
- Pick the local model by running the three headline questions on the demo
  laptop (see `docs/demo-runbook.md`).
