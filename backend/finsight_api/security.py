"""Shared-token authentication for the demo deployment.

The phone sends `Authorization: Bearer <token>`. The token is compared in
constant time. Replacing this with per-device tokens is in docs/tech-debt.md.
"""

from __future__ import annotations

import hmac

from fastapi import Request

from .errors import APIError


def require_token(request: Request) -> None:
    expected: str = request.app.state.services.settings.api_token
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(
        token.strip().encode(), expected.encode()
    ):
        raise APIError(401, "unauthorized", "Missing or wrong API token.")
