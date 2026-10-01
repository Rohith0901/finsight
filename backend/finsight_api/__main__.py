"""Run the API: `python -m finsight_api`.

HTTPS is the default, with the self-signed certificate made by
scripts/gen_cert.sh; the app pins its SHA-256 fingerprint. Plain HTTP is only
for local testing and must be asked for with FINSIGHT_ALLOW_HTTP=1.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn


def main() -> None:
    host = os.environ.get("FINSIGHT_HOST", "0.0.0.0")
    port = int(os.environ.get("FINSIGHT_PORT", "8443"))
    cert = os.environ.get("FINSIGHT_TLS_CERT", "certs/finsight.crt")
    key = os.environ.get("FINSIGHT_TLS_KEY", "certs/finsight.key")
    allow_http = os.environ.get("FINSIGHT_ALLOW_HTTP", "") == "1"

    tls: dict = {}
    if Path(cert).exists() and Path(key).exists():
        tls = {"ssl_certfile": cert, "ssl_keyfile": key}
    elif not allow_http:
        sys.exit(
            f"No TLS certificate at {cert}. Run scripts/gen_cert.sh first, "
            "or set FINSIGHT_ALLOW_HTTP=1 for local testing only."
        )
    uvicorn.run("finsight_api.main:app_factory", factory=True, host=host, port=port,
                access_log=False, **tls)


if __name__ == "__main__":
    main()
