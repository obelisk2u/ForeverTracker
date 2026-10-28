from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import admin, health, ingest, public
from app.config import get_settings
from app.observability import RequestContextMiddleware, configure_logging

DESCRIPTION = """
ForeverTracker collects **observed** World of Warcraft: Forever dungeon history from addon users
and reconciles overlapping observations into character histories.

All data is self-reported by addon users. Nothing here is verified by Blizzard. Every metric
carries its source, status and coverage; unavailable values are `null`, never zero.
"""


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    app = FastAPI(
        title="ForeverTracker API",
        version="0.1.0",
        description=DESCRIPTION,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-ForeverTracker-Client", "X-Request-ID"],
        max_age=600,
    )

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        errors = [{"loc": e.get("loc"), "type": e.get("type"), "msg": e.get("msg")} for e in exc.errors()[:10]]
        return JSONResponse(status_code=422, content={"error": "invalid_request", "detail": errors})

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        logging.getLogger("forevertracker").exception("unhandled error")
        return JSONResponse(status_code=500, content={"error": "internal_error", "detail": "unexpected server error"})

    app.include_router(health.router)
    app.include_router(public.router)
    app.include_router(ingest.router)
    app.include_router(admin.router)
    return app


app = create_app()
