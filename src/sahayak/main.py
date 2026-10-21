"""FastAPI application factory and operational HTTP endpoints."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Sequence
from contextlib import asynccontextmanager
from typing import Protocol

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from sahayak.core.config import Settings, get_settings
from sahayak.core.request_id import (
    REQUEST_ID_HEADER,
    get_request_id,
    new_request_id,
    reset_request_id,
    set_request_id,
)

logger = logging.getLogger(__name__)


class ReadinessCheck(Protocol):
    """An injected dependency probe used by the readiness endpoint."""

    def __call__(self) -> Awaitable[bool]:
        """Return whether a required dependency can serve requests."""


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a correlation ID to every HTTP request and response."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Use an inbound ID when present, otherwise create a new ULID."""
        request_id = request.headers.get(REQUEST_ID_HEADER) or new_request_id()
        request.state.request_id = request_id
        token = set_request_id(request_id)
        try:
            response = await call_next(request)
        finally:
            reset_request_id(token)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


def create_app(
    *,
    settings: Settings | None = None,
    readiness_checks: Sequence[ReadinessCheck] = (),
) -> FastAPI:
    """Build the stateless HTTP application.

    Args:
        settings: Configuration override for composition roots and tests.
        readiness_checks: Async probes for dependencies needed to accept traffic.

    Returns:
        A configured FastAPI application.
    """
    app_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield

    app = FastAPI(title=app_settings.app_name, lifespan=lifespan)
    app.add_middleware(RequestIDMiddleware)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request,
        _error: Exception,
    ) -> JSONResponse:
        """Return a stable safe error without exposing implementation details."""
        request_id = (
            getattr(request.state, "request_id", None) or get_request_id() or new_request_id()
        )
        logger.exception("unhandled HTTP exception request_id=%s", request_id)
        response = JSONResponse(
            status_code=500,
            content={"detail": "An unexpected error occurred.", "request_id": request_id},
        )
        response.headers[REQUEST_ID_HEADER] = request_id
        return response

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        """Report liveness whenever the process can answer HTTP requests."""
        return {"status": "ok"}

    @app.get("/readyz", include_in_schema=False)
    async def readyz() -> Response:
        """Report readiness only when every configured dependency probe passes."""
        for readiness_check in readiness_checks:
            if not await readiness_check():
                return JSONResponse(status_code=503, content={"status": "not_ready"})
        return JSONResponse(status_code=200, content={"status": "ok"})

    return app


app = create_app()
