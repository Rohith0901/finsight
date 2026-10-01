#!/usr/bin/env bash
# Self-signed TLS certificate for the demo laptop. The app pins its SHA-256
# fingerprint, so the laptop's IP can change (hotspot) without a new certificate.
# Uses a config file rather than -addext, so it works with both OpenSSL (Linux,
# Homebrew) and the LibreSSL that macOS ships as `openssl`.
set -euo pipefail
mkdir -p certs
cfg="$(mktemp)"
trap 'rm -f "$cfg"' EXIT
cat > "$cfg" <<'CONF'
[req]
distinguished_name = dn
x509_extensions = v3
prompt = no
[dn]
CN = finsight-demo
[v3]
subjectAltName = DNS:localhost,IP:127.0.0.1,IP:10.0.2.2
basicConstraints = critical,CA:FALSE
CONF
openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
  -keyout certs/finsight.key -out certs/finsight.crt -config "$cfg"
chmod 600 certs/finsight.key
echo
echo "Paste this fingerprint into the app (Settings > Server > Certificate fingerprint):"
openssl x509 -in certs/finsight.crt -noout -fingerprint -sha256 | cut -d= -f2 | tr -d ':' | tr 'A-F' 'a-f'
