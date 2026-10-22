"""FastAPI application factory and operational HTTP endpoints."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Sequence
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, Protocol

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from sahayak.core.auth.jwt import ALLOWED_ALGORITHMS, JWTValidator
from sahayak.core.auth.middleware import AuthMiddleware
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
from sahayak.core.security import (
    OriginValidationMiddleware,
    RequestBodyLimitMiddleware,
    SecurityHeadersMiddleware,
)
from sahayak.shared.users.service import UserService

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
    jwt_validator: JWTValidator | None = None,
    user_service: UserService | None = None,
) -> FastAPI:
    """Build the stateless HTTP application.

    Args:
        settings: Configuration override for composition roots and tests.
        readiness_checks: Async probes for dependencies needed to accept traffic.
        deps: Injected shared infrastructure for feature modules.
        registry: Explicit module registry for testing isolation.
        enable_mcp: Whether to mount the MCP Streamable HTTP endpoint.
        jwt_validator: Injected JWT validator. If None and configured, created from settings.
        user_service: Injected user provisioning service.

    Returns:
        A configured FastAPI application.
    """
    app_settings = settings or get_settings()

    validator = jwt_validator
    if validator is None and app_settings.oidc_issuer is not None:
        jwks_url = (
            str(app_settings.oidc_jwks_url)
            if app_settings.oidc_jwks_url
            else f"{app_settings.oidc_issuer}/.well-known/jwks.json"
        )
        validator = JWTValidator(
            issuer=str(app_settings.oidc_issuer),
            audience=app_settings.oidc_audience,
            jwks_url=jwks_url,
            cache=deps.cache if deps else None,
        )

    users_svc = user_service
    if users_svc is None and deps is not None and deps.session_factory is not None:
        users_svc = UserService(session_factory=deps.session_factory)

    if deps is not None and deps.session_factory is not None:
        from sahayak.core.idempotency import IdempotencyService, set_default_idempotency_service

        set_default_idempotency_service(IdempotencyService(session_factory=deps.session_factory))

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

    @app.get("/metrics", include_in_schema=False)
    async def metrics(request: Request) -> Response:
        """Report Prometheus metrics, authenticated by metrics_token when configured."""
        if app_settings.metrics_token is not None:
            auth_header = request.headers.get("Authorization", "")
            token_val = app_settings.metrics_token.get_secret_value()
            header_match = auth_header == f"Bearer {token_val}"
            x_header_match = request.headers.get("X-Metrics-Token") == token_val
            if not (header_match or x_header_match):
                return JSONResponse(status_code=401, content={"detail": "Unauthorized"})

        from sahayak.core.observability.metrics import render_metrics

        data, content_type = render_metrics()
        return Response(content=data, media_type=content_type)

    @app.get("/.well-known/oauth-protected-resource", include_in_schema=False)
    async def oauth_protected_resource() -> dict[str, Any]:
        """Expose RFC 9728 OAuth 2.0 protected resource metadata per ADR 0003."""
        auth_servers: list[str] = []
        if app_settings.oidc_issuer is not None:
            auth_servers.append(str(app_settings.oidc_issuer))

        return {
            "resource": str(app_settings.public_base_url),
            "authorization_servers": auth_servers,
            "scopes_supported": ["academics.read", "academics.write"],
            "bearer_methods_supported": ["header"],
            "resource_signing_alg_values_supported": list(ALLOWED_ALGORITHMS),
        }

    if mcp_app is not None:
        mount_mcp_server(app, mcp_app)

    # AuthMiddleware wraps MCPRoutingMiddleware so credentials are set for tool execution
    app.add_middleware(AuthMiddleware, validator=validator, user_service=users_svc)
    # Request body size limiter
    app.add_middleware(
        RequestBodyLimitMiddleware, max_body_bytes=app_settings.max_request_body_bytes
    )
    # Origin validation for web clients and DNS-rebinding protection
    allowed_origins = [str(o) for o in app_settings.allowed_origins]
    app.add_middleware(OriginValidationMiddleware, allowed_origins=allowed_origins)
    # Defense-in-depth security headers
    app.add_middleware(SecurityHeadersMiddleware)
    # RequestIDMiddleware is outermost so correlation IDs span all layers
    app.add_middleware(RequestIDMiddleware)

    return app


app = create_app()
