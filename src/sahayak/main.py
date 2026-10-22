"""FastAPI application factory and operational HTTP endpoints."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Sequence
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Protocol

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from sahayak.core.config import Settings, get_settings
from sahayak.core.mcp_server import create_mcp_app, create_mcp_server, mount_mcp_server
from sahayak.core.module import Deps, ModuleRegistry, get_registry
from sahayak.core.request_id import (
    REQUEST_ID_HEADER,
    get_request_id,
    new_request_id,
    reset_request_id,
    set_request_id,
)

if TYPE_CHECKING:
    from starlette.applications import Starlette

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
    deps: Deps | None = None,
    registry: ModuleRegistry | None = None,
    enable_mcp: bool = True,
) -> FastAPI:
    """Build the stateless HTTP application.

    Args:
        settings: Configuration override for composition roots and tests.
        readiness_checks: Async probes for dependencies needed to accept traffic.
        deps: Injected shared infrastructure for feature modules.
        registry: Explicit module registry for testing isolation.
        enable_mcp: Whether to mount the MCP Streamable HTTP endpoint.

    Returns:
        A configured FastAPI application.
    """
    app_settings = settings or get_settings()

    mcp_app: Starlette | None = None
    if enable_mcp:
        mod_registry = registry or get_registry()
        if not mod_registry.modules:
            try:
                mod_registry.load(app_settings.enabled_modules)
            except RuntimeError as exc:
                logger.warning(
                    "could not load configured modules %s: %s",
                    app_settings.enabled_modules,
                    exc,
                )
                if "_template" not in mod_registry.modules:
                    mod_registry.load(("_template",))

        mcp_server = create_mcp_server(
            settings=app_settings,
            deps=deps,
            registry=mod_registry,
        )
        mcp_app = create_mcp_app(mcp_server, settings=app_settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        if mcp_app is not None:
            async with mcp_app.router.lifespan_context(mcp_app):
                yield
        else:
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

    if mcp_app is not None:
        mount_mcp_server(app, mcp_app)

    return app


app = create_app()
