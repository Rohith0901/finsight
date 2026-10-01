# FinSight common commands. Run `make setup` once.
# Newest suitable Python on PATH. macOS's own python3 is 3.9, which is too old;
# `brew install python@3.12` (or use Docker: docker compose up --build).
PY ?= $(shell for p in python3.12 python3.13 python3.11 python3.14 python3; do \
        command -v $$p >/dev/null 2>&1 && { echo $$p; break; }; done)
VENV = .venv
BIN = $(VENV)/bin

setup:            ## Python env for backend + ML
	@$(PY) -c 'import sys; sys.exit(sys.version_info < (3, 11))' || \
	  { echo "Python 3.11+ is needed ($(PY) is older). On macOS: brew install python@3.12"; exit 1; }
	$(PY) -m venv $(VENV)
	$(BIN)/pip install -U pip
	$(BIN)/pip install -e "backend[dev]" -r ml/requirements.txt

token:            ## print a new API token
	@scripts/new_token.sh

cert:             ## self-signed TLS cert + fingerprint for the app
	scripts/gen_cert.sh

serve:            ## run the API on https://0.0.0.0:8443 (needs .env and certs/)
	set -a; . ./.env; set +a; $(BIN)/python -m finsight_api

test:             ## backend + ML tests and lint
	$(BIN)/ruff check backend ml
	cd backend && ../$(BIN)/python -m pytest
	cd ml && ../$(BIN)/python -m pytest

train:            ## retrain the classifier into backend/models/classifier/v1
	cd ml && ../$(BIN)/python -m finsight_ml.train

eval:             ## full evaluation -> ml/reports/latest.md
	cd ml && ../$(BIN)/python -m finsight_ml.evaluate

fixtures:         ## regenerate parser fixtures, demo SMS and app asset copies
	cd ml && ../$(BIN)/python -m finsight_ml.build_fixtures

app:              ## build the Android APK end to end (needs Flutter + Android SDK)
	scripts/build_app.sh

app-install:      ## build and install on the phone connected by USB
	scripts/build_app.sh --install

app-test:         ## Flutter analyzer + tests (needs Flutter on this machine)
	cd app && flutter pub get && flutter analyze --no-fatal-infos && flutter test

.PHONY: setup token cert serve test train eval fixtures app app-install app-test
