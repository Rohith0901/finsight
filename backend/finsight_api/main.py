"""App factory. `uvicorn finsight_api.main:app` or `python -m finsight_api`."""

from __future__ import annotations

import logging

from fastapi import FastAPI

from . import API_VERSION, __version__, errors
from .api.v1 import router
from .config import Settings, load_settings
from .llm.base import Provider
from .middleware import AccessLog, BodyLimit
from .services import build_services


def create_app(settings: Settings | None = None,
               providers: dict[str, Provider] | None = None) -> FastAPI:
    settings = settings or load_settings()
    app = FastAPI(
        title="FinSight API",
        version=__version__,
        description="Stateless service: every request carries its data, nothing is stored.",
        docs_url="/docs",
        redoc_url=None,
    )
    app.state.services = build_services(settings, providers)
    errors.install(app)
    app.include_router(router)

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict:
        return {"status": "ok", "api_version": API_VERSION}

    # Outermost first: log every request, then enforce the size limit.
    app.add_middleware(BodyLimit, max_bytes=settings.max_body_bytes)
    app.add_middleware(AccessLog)
    return app


def _configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def app_factory() -> FastAPI:
    _configure_logging()
    return create_app()
