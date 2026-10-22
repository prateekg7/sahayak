"""Unit tests for HTTP security hardening: headers, origin, body limits, outbound allow-list."""

from __future__ import annotations

import httpx
import pytest
from pydantic import AnyUrl

from sahayak.core.config import Settings
from sahayak.core.security import HostBlockedError, create_safe_http_client
from sahayak.main import create_app


@pytest.mark.asyncio
async def test_security_headers_injected_on_all_responses() -> None:
    """Every HTTP response contains defense-in-depth security headers."""
    app = create_app(enable_mcp=False)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        res = await client.get("/healthz")
        assert res.status_code == 200
        expected_hsts = "max-age=63072000; includeSubDomains; preload"
        assert res.headers["strict-transport-security"] == expected_hsts
        assert res.headers["x-content-type-options"] == "nosniff"
        assert res.headers["x-frame-options"] == "DENY"
        assert res.headers["referrer-policy"] == "no-referrer"
        assert res.headers["content-security-policy"] == "default-src 'none'"


@pytest.mark.asyncio
async def test_origin_validation_allows_valid_and_rejects_unauthorized() -> None:
    """Origin validation rejects unauthorized origins with 403 Forbidden."""
    settings = Settings(
        allowed_origins=(AnyUrl("https://alexa.amazon.com"), AnyUrl("https://developer.amazon.com"))
    )
    app = create_app(settings=settings, enable_mcp=False)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        # 1. Allowed origin succeeds
        res_ok = await client.get("/healthz", headers={"Origin": "https://alexa.amazon.com"})
        assert res_ok.status_code == 200

        # 2. Unauthorized origin rejected
        res_bad = await client.get("/healthz", headers={"Origin": "https://attacker.evil.com"})
        assert res_bad.status_code == 403
        assert "Invalid Origin" in res_bad.text

        # 3. No origin header (server-to-server) succeeds
        res_none = await client.get("/healthz")
        assert res_none.status_code == 200


@pytest.mark.asyncio
async def test_request_body_size_limit_rejects_oversized_payload() -> None:
    """Requests with payloads exceeding max_request_body_bytes are rejected with 413."""
    # Configure tiny 100-byte max body size
    settings = Settings(max_request_body_bytes=100)
    app = create_app(settings=settings, enable_mcp=False)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        # Small payload (under 100 bytes)
        res_small = await client.post("/healthz", content=b"a" * 50)
        # Note: /healthz does not allow POST, returns 405 (meaning it was not rejected with 413)
        assert res_small.status_code == 405

        # Large payload (200 bytes > 100 max)
        res_large = await client.post("/healthz", content=b"a" * 200)
        assert res_large.status_code == 413
        assert "Payload Too Large" in res_large.text


@pytest.mark.asyncio
async def test_outbound_http_allow_list_blocks_unauthorized_hosts() -> None:
    """create_safe_http_client prevents outbound requests to unapproved hosts."""
    allowed_hosts = ["en.wikipedia.org", "generativelanguage.googleapis.com"]

    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=f"OK from {request.url.host}")

    mock_transport = httpx.MockTransport(mock_handler)
    async with create_safe_http_client(
        allowed_hosts=allowed_hosts, transport=mock_transport
    ) as safe_client:
        # 1. Allowed host succeeds
        res_wiki = await safe_client.get("https://en.wikipedia.org/wiki/Test")
        assert res_wiki.status_code == 200

        # 2. Blocked host raises HostBlockedError before sending traffic
        with pytest.raises(HostBlockedError) as exc_info:
            await safe_client.get("https://malicious.site.com/exploit")
        assert exc_info.value.host == "malicious.site.com"
        assert exc_info.value.code == "host_blocked"
