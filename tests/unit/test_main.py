"""Tests for the HTTP application factory and operational endpoints."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from sahayak.core.request_id import REQUEST_ID_HEADER
from sahayak.main import create_app


@pytest_asyncio.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    """Provide an in-process client for a default application instance."""
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


@pytest.mark.asyncio
async def test_healthz_is_live_and_generates_a_request_id(client: httpx.AsyncClient) -> None:
    """Liveness is always available and has a generated correlation ID."""
    response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert len(response.headers[REQUEST_ID_HEADER]) == 26


@pytest.mark.asyncio
async def test_request_id_is_propagated_from_the_client(client: httpx.AsyncClient) -> None:
    """A caller-provided correlation ID is preserved in the response."""
    response = await client.get("/healthz", headers={REQUEST_ID_HEADER: "trace-123"})

    assert response.headers[REQUEST_ID_HEADER] == "trace-123"


@pytest.mark.asyncio
async def test_readyz_fails_when_a_dependency_check_fails() -> None:
    """Readiness returns 503 without claiming that an unhealthy dependency is usable."""

    async def unavailable() -> bool:
        return False

    app = create_app(readiness_checks=(unavailable,))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/readyz")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}


@pytest.mark.asyncio
async def test_unhandled_errors_do_not_expose_a_stack_trace() -> None:
    """Unhandled application errors are safe and retain the request correlation ID."""
    app: FastAPI = create_app()

    @app.get("/raise")
    async def raise_error() -> None:
        raise RuntimeError("secret implementation detail")

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/raise", headers={REQUEST_ID_HEADER: "trace-safe"})

    assert response.status_code == 500
    assert response.headers[REQUEST_ID_HEADER] == "trace-safe"
    assert response.json() == {
        "detail": "An unexpected error occurred.",
        "request_id": "trace-safe",
    }
    assert "secret implementation detail" not in response.text
