# FinSight

An Android app that turns bank transaction SMS into a private, explainable view of
your spending, and tells you how much you can safely spend today.

- **The phone** reads bank SMS (with consent), parses them, and keeps only the parsed
  fields in an encrypted SQLite database. The raw SMS never leaves the phone.
- **A stateless FastAPI service** on the demo laptop computes categories, recurring
  payments, unusual spending, the month-end forecast, safe-to-spend and chat answers.
  Every request carries its own data; nothing is stored.
- **The assistant** only explains numbers the backend computed. A verifier rejects any
  answer containing a number the tools didn't produce.

Design and decisions: the FinSight design doc (Claude Docs) and [docs/adr](docs/adr).

## Repository

| Path | What |
| --- | --- |
| `app/` | Flutter app (Android) |
| `backend/` | FastAPI service, financial engine, pattern models, assistant |
| `ml/` | Synthetic data, training, evaluation (`ml/reports/latest.md`) |
| `shared/` | Contracts both sides read: categories, merchants, SMS hints, test fixtures |
| `docs/` | ADRs, API reference, onboarding, demo runbook, tech-debt register, deploy checklist |

## Quick start: backend (about 5 minutes)

```bash
make setup                   # Python 3.11+ virtualenv with backend + ML
cp .env.example .env         # then put the output of `make token` in FINSIGHT_API_TOKEN
make cert                    # self-signed cert; note the fingerprint it prints
make test                    # lint + backend + ML tests
make serve                   # https://0.0.0.0:8443
curl -k https://127.0.0.1:8443/healthz
```

Or with Docker: `docker compose up --build` (same `.env` and `certs/`).

The assistant uses a local model through [Ollama](https://ollama.com) by default:
`ollama pull qwen2.5:3b`. With no model running, chat still works from templates.

## Quick start: app

```bash
scripts/build_app.sh --install   # Flutter 3.35+ and Android Studio needed
```

That generates the Android build files, runs the analyzer and tests, builds
`finsight-demo.apk` and installs it on the phone plugged in by USB. Without
Flutter installed, push to GitHub and download the APK that the `app`
workflow builds (Actions > app > Artifacts). Details: [app/README.md](app/README.md).

## On a Mac

Everything here is built and run on a Mac (Apple silicon or Intel); only the
app itself runs on Android.

| Part | On the Mac |
| --- | --- |
| Backend | `docker compose up --build` with Docker Desktop, or `make setup && make serve` with Python 3.11+ (`brew install python@3.12`; macOS's own `python3` is 3.9 and too old) |
| Local model | The [Ollama](https://ollama.com) Mac app, then `ollama pull qwen2.5:3b` |
| App build | Flutter and Android Studio, then `scripts/build_app.sh` |
| Trying the app without a phone | Android Studio's emulator: `flutter run`, tap "Try with demo data instead". The emulator reaches the Mac's backend at `https://10.0.2.2:8443` |
| Real SMS | Only on an Android phone; iPhones and Macs don't let apps read messages |

The first time the backend runs, macOS asks whether to accept incoming network
connections: allow it, or the phone can't connect.

## Evaluation

`make eval` retrains on synthetic data and writes `ml/reports/latest.md`. Read its
banner: synthetic numbers are optimistic. Results on your own masked messages
(`ml/data/README.md`) are the ones to present.
