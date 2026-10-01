# ADR-004: Encrypted local database

Status: Accepted (revised 2026-10-01)
Date: 2026-09-30 · Deciders: the team

## Context

The app needs an encrypted SQL store with migrations, because the schema will
change during the project. The plan was a week-1 spike between Drift (typed
queries) and sqflite_sqlcipher (raw SQL).

## Decision (as built)

`sqflite_sqlcipher` with raw SQL in one `Repository` class. The 256-bit key and
the person-pseudonym salt are generated on first launch and stored in the
Android Keystore through `flutter_secure_storage`. Schema version 1 is defined
in `lib/data/database.dart` with an `onUpgrade` hook for later versions. Tests
run the same schema on `sqflite_common_ffi` (unencrypted, in memory).

## Why the revision

- Drift needs code generation (`build_runner`), which adds a build step and
  generated files to review, for a schema of eight tables.
- The aggregations that would benefit from typed queries run on the server
  (ADR-001), so the phone mostly inserts, lists and updates.
- One dependency fewer between the app and SQLCipher.

## Options considered

| Option | For | Against |
| --- | --- | --- |
| Drift + SQLCipher | Typed queries, migrations | Codegen; encryption setup to prove |
| **sqflite_sqlcipher (chosen)** | Thin, proven, raw SQL | Queries are strings; tests must cover them |
| Isar / ObjectBox | Fast | Weak fit for grouped, date-ranged queries |

## Consequences

- Repository tests (`test/pipeline_test.dart`) are the guard on SQL strings.
- Still to do from the original spike criteria: a v1 to v2 migration test
  (tracked in `docs/tech-debt.md`).
- Losing the Keystore entry (factory reset, some backup restores) makes the
  database unreadable; the app then starts fresh. `allowBackup` is off.
