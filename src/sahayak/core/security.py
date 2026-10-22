"""HTTP security hardening: security headers, origin check, body limits, outbound allow-list."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any, cast

import httpx
from fastapi import Response

from sahayak.core.errors import SahayakError

logger = logging.getLogger(__name__)


class SecurityError(SahayakError):
    """Base class for HTTP and transport security violations."""

    code: str = "security_violation"


class HostBlockedError(SecurityError):
    """Raised when an outbound HTTP call targets a host not in the allow-list."""

    code: str = "host_blocked"

    def __init__(self, host: str) -> None:
        super().__init__(
            spoken="An external request was blocked for security reasons.",
            detail=f"Outbound host '{host}' is not in the allow-list.",
        )
        self.host = host


class PayloadTooLargeError(SecurityError):
    """Raised when a request body exceeds the configured maximum size."""

    code: str = "payload_too_large"


class InvalidOriginError(SecurityError):
    """Raised when an Origin header fails allow-list validation."""

    code: str = "invalid_origin"


class SecurityHeadersMiddleware:
    """Inject standard HTTP defense-in-depth headers into all responses."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Any,
        send: Any,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                hsts_val = b"max-age=63072000; includeSubDomains; preload"
                headers.append((b"strict-transport-security", hsts_val))
                headers.append((b"x-content-type-options", b"nosniff"))
                headers.append((b"x-frame-options", b"DENY"))
                headers.append((b"referrer-policy", b"no-referrer"))
                headers.append((b"content-security-policy", b"default-src 'none'"))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)


class OriginValidationMiddleware:
    """Validate incoming Origin header against configured allowed origins."""

    def __init__(self, app: Any, allowed_origins: Sequence[str] = ()) -> None:
        self.app = app
        self.allowed_origins = {o.rstrip("/") for o in allowed_origins}

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Any,
        send: Any,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if self.allowed_origins:
            headers = dict(scope.get("headers", []))
            origin_bytes = headers.get(b"origin")
            if origin_bytes:
                origin = origin_bytes.decode("latin1").rstrip("/")
                if origin not in self.allowed_origins:
                    logger.warning("rejected request from unauthorized origin: %s", origin)
                    resp = Response(
                        content="Forbidden: Invalid Origin",
                        status_code=403,
                        media_type="text/plain",
                    )
                    await resp(scope, receive, send)
                    return

        await self.app(scope, receive, send)


class RequestBodyLimitMiddleware:
    """Reject request bodies exceeding the maximum configured byte size."""

    def __init__(self, app: Any, max_body_bytes: int = 65536) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Any,
        send: Any,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        content_length_bytes = headers.get(b"content-length")
        if content_length_bytes:
            try:
                content_length = int(content_length_bytes.decode("ascii"))
                if content_length > self.max_body_bytes:
                    logger.warning(
                        "rejected request with Content-Length %d > %d",
                        content_length,
                        self.max_body_bytes,
                    )
                    resp = Response(
                        content="Payload Too Large",
                        status_code=413,
                        media_type="text/plain",
                    )
                    await resp(scope, receive, send)
                    return
            except ValueError:
                pass

        bytes_received = 0

        async def limited_receive() -> dict[str, Any]:
            nonlocal bytes_received
            message = await receive()
            if message["type"] == "http.request":
                body = message.get("body", b"")
                bytes_received += len(body)
                if bytes_received > self.max_body_bytes:
                    raise PayloadTooLargeError()
            return cast(dict[str, Any], message)

        try:
            await self.app(scope, limited_receive, send)
        except PayloadTooLargeError:
            logger.warning("request body stream exceeded max size %d", self.max_body_bytes)
            resp = Response(
                content="Payload Too Large",
                status_code=413,
                media_type="text/plain",
            )
            await resp(scope, receive, send)


def create_safe_http_client(
    allowed_hosts: Sequence[str] | set[str] | None = None,
    *,
    timeout: float = 5.0,
    **kwargs: Any,
) -> httpx.AsyncClient:
    """Create an httpx.AsyncClient that restricts outbound requests to allowed hosts.

    Args:
        allowed_hosts: Allowed domain names (e.g. ['en.wikipedia.org', 'auth.example.com']).
        timeout: Global request timeout in seconds.
        **kwargs: Additional options forwarded to httpx.AsyncClient.

    Returns:
        An AsyncClient configured with pre-request host validation.
    """
    hosts_set = {h.lower() for h in allowed_hosts} if allowed_hosts is not None else None

    async def check_outbound_host(request: httpx.Request) -> None:
        if hosts_set is not None:
            host = request.url.host.lower()
            if host not in hosts_set:
                logger.warning("blocked outbound HTTP request to unauthorized host: %s", host)
                raise HostBlockedError(host)

    event_hooks = dict(kwargs.pop("event_hooks", {}))
    request_hooks = list(event_hooks.get("request", []))
    request_hooks.append(check_outbound_host)
    event_hooks["request"] = request_hooks

    return httpx.AsyncClient(timeout=timeout, event_hooks=event_hooks, **kwargs)
