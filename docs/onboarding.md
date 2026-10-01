# Onboarding

For a new team member (or the examiner reading the code). About an hour gets
you from clone to a running backend, a passing test suite and the app on a
phone.

## 1. The picture

```
 Phone (Flutter, Android)                         Laptop (FastAPI, Docker)
 ┌───────────────────────────────┐   HTTPS +      ┌──────────────────────────┐
 │ SMS inbox ─► Kotlin channel   │   pinned cert  │ /v1/classify  (model)    │
 │   (drops personal numbers)    │   + token      │ /v1/insights  recurring, │
 │ parser ─► normaliser ─► rules │ ─────────────► │   anomalies, forecast,   │
 │ encrypted SQLite (SQLCipher)  │  transactions  │   safe-to-spend          │
 │ screens ◄─ insights cache     │ ◄───────────── │ /v1/chat ─► Ollama/Gemini│
 └───────────────────────────────┘   results      │   + verifier             │
                                                  │ stores nothing           │
 shared/: categories, merchants, SMS hints, fixtures — read by both sides
```

Read, in order: the root `README.md`, `docs/adr/` (seven one-page decisions),
`docs/api.md`, then `ml/reports/latest.md`.

## 2. Set up

You need Python 3.11+, Docker (optional), Flutter 3.35+, Android Studio and
Ollama (optional).

```bash
git clone <repo> && cd finsight
make setup && make test          # 39 backend + 10 ML tests, lint
cp .env.example .env             # FINSIGHT_API_TOKEN=$(make token)
make cert && make serve          # https://0.0.0.0:8443
cd app && flutter create --platforms=android --org com.finsight --project-name finsight .
flutter pub get && flutter test && flutter run
```

Details for the app are in `app/README.md`.

## 3. Conventions that matter

- **Money is integer paise** everywhere: database, API, engine. Rupees appear
  only in UI strings and assistant text. Never use floats for money.
- **Dates.** Timestamps are stored and sent in UTC; "today" and month
  boundaries use the user's local date (`as_of`).
- **The SMS body never leaves the parser.** Not in the database, logs, crash
  reports, API calls or test snapshots. Debug exports go through
  `maskBody()` and are read by a human before sharing.
- **Twins.** Three pieces exist in Python and Dart and must behave identically:
  the SMS parser (`ml/finsight_ml/parser_ref.py` ↔
  `app/lib/ingestion/sms_parser.dart`), the merchant normaliser
  (`ml/finsight_ml/names.py` ↔ `app/lib/ingestion/normalizer.dart`) and the
  hint matcher. Shared fixtures in `shared/fixtures/` are the contract; both
  test suites run them.
- **Shared contracts** live in `shared/*.json`. After editing one, run
  `make fixtures` (it refreshes `app/assets/shared/`; a Flutter test fails if
  the copies drift).
- **Schemas reject unknown fields** (`extra="forbid"`). Adding a field to the
  app's request means adding it to `backend/finsight_api/schemas.py` first.
- Lint: `ruff` for Python (`ruff.toml`), `flutter analyze` for Dart
  (`app/analysis_options.yaml`, single quotes).

## 4. Common changes

### Add a bank SMS template

1. Add a renderer to `ml/finsight_ml/sms_render.py` with the fields it should
   parse to (copy a masked real message's structure; never commit a real one).
2. Run `cd ml && python -m finsight_ml.parser_ref`. If it isn't 100%, change
   `parser_ref.py` until it is.
3. Make the same change, regex for regex, in `sms_parser.dart`. Python `re.I`
   becomes `caseSensitive: false`, `re.M` becomes `multiLine: true`;
   `re.match` is anchored at the start, Dart `firstMatch` is not.
4. `make fixtures`, `make test`, `flutter test`.
5. Add a few masked real examples to `shared/fixtures/sms_real.jsonl`.

### Add a merchant

Add it to `shared/merchants.json` with its category and aliases (aliases of
5+ characters match inside other text; shorter ones only as whole words), add
a case to `shared/fixtures/merchant_name_cases.json` if it's tricky, then
`make fixtures` and both test suites. Retrain if the merchant appears in
synthetic data (`make train && make eval`).

### Add an API endpoint

Schema in `schemas.py` (with `extra="forbid"` and limits), logic in
`engine/` or `ml/`, route in `api/v1.py`, a test in `backend/tests/test_api.py`,
a client method in `app/lib/api/api_client.dart` with a `MockClient` test, and
a row in `docs/api.md`.

### Add an assistant question

Add an intent (pattern and handler) in `backend/finsight_api/llm/intents.py`.
Handlers only format numbers that tools computed. Add matching and answer
tests in `backend/tests/test_assistant.py`.

## 5. Pull requests

- One area per PR, reviewed by that area's second person.
- CI must pass: `backend.yml` (ruff, pytest) and `app.yml` (analyze, test).
- Touching parsing, normalising or `toApi()`? Say so in the PR description;
  those are the privacy-critical paths.
- Changing a decision? Add or revise an ADR in the same PR.
- New shortcut or known gap? Add it to `docs/tech-debt.md`.

## 6. Where to ask

The design doc (Claude Docs) has the requirements and the reasoning behind
each ADR. For anything else, ask the area owner listed there.
