"""Auto-discovery user isolation security tests for all registered tools (T1.9)."""

from __future__ import annotations

import json

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from sahayak.core.auth.jwt import JWTValidator
from sahayak.core.config import get_settings
from sahayak.core.mcp_server import create_mcp_server
from sahayak.core.module import ModuleRegistry
from sahayak.main import create_app
from tests.security.isolation import (
    ISOLATION_REGISTRY,
    assert_user_isolation,
    get_untested_tools,
)


@pytest.fixture(scope="module")
def sec_rsa_key() -> rsa.RSAPrivateKey:
    """Generate RSA key for security regression tests."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def test_every_registered_tool_has_isolation_specification() -> None:
    """Auto-discovery gate: fails CI if any registered tool lacks isolation coverage."""
    settings = get_settings()
    registry = ModuleRegistry()
    registry.load(("_template",))
    server = create_mcp_server(settings=settings, registry=registry)

    untested = get_untested_tools(server)
    if untested:
        pytest.fail(
            f"The following tools lack user isolation test coverage: {untested}. "
            "Every MCP tool must register an isolation specification in "
            "tests/security/isolation.py."
        )


@pytest.mark.asyncio
async def test_auto_isolation_suite_passes_all_registered_tools(
    sec_rsa_key: rsa.RSAPrivateKey,
) -> None:
    """Run assert_user_isolation across all registered tool specifications."""
    jwk_dict = dict(json.loads(RSAAlgorithm.to_jwk(sec_rsa_key.public_key())))
    jwk_dict["kid"] = "sec-test-key"
    jwks = {"keys": [jwk_dict]}

    transport_mock = httpx.MockTransport(lambda _: httpx.Response(200, json=jwks))
    async with httpx.AsyncClient(transport=transport_mock) as http_client:
        validator = JWTValidator(
            issuer="https://auth.example.com",
            audience="sahayak-api",
            jwks_url="https://auth.example.com/.well-known/jwks.json",
            http_client=http_client,
        )

        registry = ModuleRegistry()
        registry.load(("_template",))
        app = create_app(registry=registry, jwt_validator=validator)

        async with app.router.lifespan_context(app):
            for spec in ISOLATION_REGISTRY.values():
                await assert_user_isolation(spec, app=app, rsa_key=sec_rsa_key)
