#!/usr/bin/env bash
# Prints a random API token for FINSIGHT_API_TOKEN (and the app's Settings screen).
set -euo pipefail
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
