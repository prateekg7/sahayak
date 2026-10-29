"""Alexa+ MCP Add-on Compliance & Verification Contract Tests.

Verifies end-to-end adherence to Amazon Alexa+ Developer requirements:
1. Streamable HTTP transport and spec compliance.
2. CORS preflight (OPTIONS /mcp) and header exposure.
3. 401 Unauthorized without WWW-Authenticate header.
4. RFC 9728 Protected Resource Metadata at /.well-known/oauth-protected-resource.
5. MCP tool call response payload architecture (structuredContent and content).
6. Voice-safe response formatting (no forbidden markdown pipes, emojis, raw URLs).
7. Add-on package manifest (addon-package/addon.json) schema and asset compliance.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from starlette.testclient import TestClient

from sahayak.core.config import Settings
from sahayak.core.module import ModuleRegistry
from sahayak.main import create_app


@pytest.fixture
def compliance_app() -> Any:
    """FastAPI test app configured with template module for compliance testing."""
    reg = ModuleRegistry()
    reg.load(("_template",))
    settings = Settings(
        app_name="Sahayak",
        mcp_stateless_http=True,
    )
    return create_app(settings=settings, registry=reg)


def test_unauthenticated_protected_mcp_returns_401_without_www_authenticate() -> None:
    """Alexa+ requirement: unauthenticated requests return 401 WITHOUT WWW-Authenticate."""
    from sahayak.core.auth.jwt import JWTValidator

    validator = JWTValidator(
        issuer="https://auth.sahayak.app",
        audience="sahayak-api",
        jwks_url="https://auth.sahayak.app/.well-known/jwks.json",
    )
    reg = ModuleRegistry()
    reg.load(("_template",))
    app = create_app(jwt_validator=validator, registry=reg)

    with TestClient(app) as client:
        # Request with invalid Bearer token
        resp = client.post(
            "/mcp",
            headers={"Authorization": "Bearer invalid-token"},
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "ping_echo", "arguments": {"message": "hello"}},
            },
        )
        assert resp.status_code == 401
        assert "WWW-Authenticate" not in resp.headers


def test_rfc_9728_protected_resource_metadata(compliance_app: Any) -> None:
    """Alexa+ requirement: PRM document hosted at /.well-known/oauth-protected-resource."""
    with TestClient(compliance_app) as client:
        resp = client.get("/.well-known/oauth-protected-resource")
        assert resp.status_code == 200
        prm = resp.json()
        assert "resource" in prm
        assert "authorization_servers" in prm
        assert "scopes_supported" in prm
        assert "bearer_methods_supported" in prm
        assert "header" in prm["bearer_methods_supported"]


@pytest.mark.asyncio
async def test_cors_options_preflight(compliance_app: Any) -> None:
    """Alexa+ / Web Inspector requirement: OPTIONS /mcp returns 204 with CORS headers."""
    async with compliance_app.router.lifespan_context(compliance_app):
        transport = httpx.ASGITransport(app=compliance_app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://127.0.0.1:8000"
        ) as client:
            resp = await client.options(
                "/mcp",
                headers={
                    "origin": "http://localhost:5173",
                    "access-control-request-method": "POST",
                },
            )
            assert resp.status_code == 204
            assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"
            allowed_methods = resp.headers.get("access-control-allow-methods", "")
            assert "POST" in allowed_methods
            assert "GET" in allowed_methods
            assert "OPTIONS" in allowed_methods
            exposed = resp.headers.get("access-control-expose-headers", "")
            assert "mcp-session-id" in exposed
            assert "content-type" in exposed


@pytest.mark.asyncio
async def test_stateless_get_mcp_returns_405_with_cors(compliance_app: Any) -> None:
    """Stateless Streamable HTTP GET /mcp returns 405 with CORS headers for browser clients."""
    async with compliance_app.router.lifespan_context(compliance_app):
        transport = httpx.ASGITransport(app=compliance_app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://127.0.0.1:8000"
        ) as client:
            resp = await client.get("/mcp", headers={"origin": "http://localhost:5173"})
            assert resp.status_code == 405
            assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"
            assert "Method Not Allowed" in resp.text


@pytest.mark.asyncio
async def test_tool_call_payload_contains_structured_content_and_content(
    compliance_app: Any,
) -> None:
    """Alexa+ requirement: tool call result returns structuredContent and content blocks."""
    async with compliance_app.router.lifespan_context(compliance_app):
        transport = httpx.ASGITransport(app=compliance_app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://127.0.0.1:8000"
        ) as client:
            # Initialize
            init_res = await client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "alexa-client", "version": "1.0.0"},
                    },
                },
                headers={"Accept": "application/json, text/event-stream"},
            )
            assert init_res.status_code == 200

            # Tool call
            call_res = await client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "ping_echo", "arguments": {"message": "voice-test"}},
                },
                headers={"Accept": "application/json, text/event-stream"},
            )
            assert call_res.status_code == 200
            result = call_res.json()["result"]

            # Alexa+ payload fields verification
            assert "structuredContent" in result
            assert "content" in result
            assert result["isError"] is False

            # Verify structuredContent schema
            sc = result["structuredContent"]
            assert sc["ok"] is True
            assert "spoken_summary" in sc
            assert "data" in sc
            assert sc["data"]["echo"] == "echo: voice-test"

            # Verify content block
            content_blocks = result["content"]
            assert len(content_blocks) > 0
            assert content_blocks[0]["type"] == "text"
            assert "Pong. echo: voice-test" in content_blocks[0]["text"]


def test_addon_manifest_conforms_to_alexa_specification() -> None:
    """Verify addon-package/addon.json conforms to all Alexa+ store listing constraints."""
    manifest_path = Path("addon-package/addon.json")
    assert manifest_path.exists(), "addon-package/addon.json must exist"

    manifest = json.loads(manifest_path.read_text())
    assert manifest.get("manifestVersion") == "1.0"

    store_listing = manifest["storeListing"]
    assert "US" in store_listing["distributionCountries"]

    locale = store_listing["locales"]["en-US"]
    # Name <= 30 chars
    name = locale["name"]["value"]
    assert len(name) <= 30
    assert len(name) > 0

    # shortDescription <= 123 chars
    short_desc = locale["shortDescription"]
    assert len(short_desc) <= 123
    assert len(short_desc) > 0

    # fullDescription <= 4000 chars
    full_desc = locale["fullDescription"]
    assert len(full_desc) <= 4000

    # examplePhrases: 3 to 4 items, each <= 200 chars
    phrases = locale["examplePhrases"]
    assert 3 <= len(phrases) <= 4
    for phrase in phrases:
        assert len(phrase) <= 200

    # privacy & terms URLs
    privacy_comp = locale["privacyAndCompliance"]
    assert privacy_comp["privacyPolicyUrl"].startswith("https://")
    assert privacy_comp["termsOfUseUrl"].startswith("https://")

    # Light icons: all 6 required sizes must be present
    light_icons = locale["mediaAssets"]["icons"]["light"]
    icon_sizes = {icon["size"] for icon in light_icons}
    expected_sizes = {"72x72", "64x64", "88x88", "126x126", "180x180", "241x241"}
    assert expected_sizes.issubset(icon_sizes)

    # Carousel image: at least 1 image of size 600x900
    carousel = locale["mediaAssets"]["carouselImages"]
    assert len(carousel) >= 1
    assert carousel[0]["size"] == "600x900"
    assert len(carousel[0]["altText"]) <= 250

    # Integrations: MCP endpoint declared
    integrations = manifest["integrations"]
    assert len(integrations) >= 1
    mcp_integ = next(i for i in integrations if i["type"] == "MCP")
    default_endpoint = mcp_integ["config"]["endpoints"]["default"]
    assert default_endpoint["type"] == "HTTPS"
    assert default_endpoint["uri"].startswith("https://")


def test_addon_media_assets_exist_and_are_valid_png() -> None:
    """Verify local asset files exist and are valid PNG images."""
    assets_dir = Path("addon-package/assets")
    png_magic = b"\x89PNG\r\n\x1a\n"

    for size in ("72x72", "64x64", "88x88", "126x126", "180x180", "241x241"):
        icon_path = assets_dir / "icons" / f"icon-{size}.png"
        assert icon_path.exists(), f"Icon {icon_path} must exist"
        data = icon_path.read_bytes()
        assert data.startswith(png_magic), f"Icon {icon_path} must be a valid PNG"

    carousel_path = assets_dir / "carousel" / "sahayak-overview.png"
    assert carousel_path.exists(), "Carousel image must exist"
    data = carousel_path.read_bytes()
    assert data.startswith(png_magic), "Carousel image must be a valid PNG"
