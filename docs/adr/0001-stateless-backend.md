# ADR-001: Stateless backend, data stays on the phone

Status: Accepted
Date: 2026-09-30 · Deciders: the four team members and the project guide

## Context

The pitch promised on-device privacy and offline use, but also listed FastAPI
and PostgreSQL. Running the models in FastAPI means some data has to reach a
server, and a server database brings accounts, authentication, consent records
and breach duties.

## Decision

The phone owns all user data. Each backend request carries the transaction
window it needs (at most 5,000 rows, 5 MB); the backend computes, answers and
keeps nothing. PostgreSQL is dropped.

What crosses the network is only `Txn.toApi()`: id, UTC timestamp, amount in
paise, direction, normalised merchant key (people as `person:<hash>`), category,
account alias (`acct_1`), mode and two flags. No SMS text, references, account
numbers or payee names. The backend's pydantic models use `extra="forbid"`, so a
client that sends more is rejected rather than silently accepted.

## Options considered

| Option | For | Against |
| --- | --- | --- |
| **Stateless backend (chosen)** | Simple, free, easiest privacy story with a server | Larger requests; no sync |
| Backend database with accounts | Sync, server-side history | Auth, consent records, breach duties, hosting |
| Fully on-device | Best privacy and offline | Porting every model to Dart is the hardest ML work |

## Consequences

- Privacy is easy to explain and to show (the access log records method, path,
  status and timing only).
- Without the laptop, the phone still captures, parses, categorises known
  merchants and people, and shows history; predictions, forecast and chat wait
  for the backend.
- No cross-device sync and no server backups. Deleting the app deletes the data.
- Revisit if offline predictions become a requirement: ADR-003 keeps that port
  cheap.
