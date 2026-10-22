"""Contract tests for RFC 9728 metadata, token challenge, and tool authorization (T1.3)."""

from __future__ import annotations

import json
import time
from typing import Any, cast

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

from sahayak.core.auth.jwt import JWTValidator
from sahayak.core.auth.principal import requires
from sahayak.core.envelope import ok
from sahayak.core.module import Deps, HealthStatus, ModuleRegistry
from sahayak.main import create_app


@pytest.fixture(scope="module")
def auth_test_rsa_key() -> rsa.RSAPrivateKey:
    """Generate RSA key for contract tests."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def make_auth_token(
    key: rsa.RSAPrivateKey,
    *,
    sub: str = "user-abc",
    scope: str = "academics.read",
) -> str:
    """Generate a signed test JWT."""
    now = int(time.time())
    payload = {
        "sub": sub,
        "iss": "https://auth.example.com",
        "aud": "sahayak-api",
        "exp": now + 3600,
        "iat": now,
        "nbf": now,
        "scope": scope,
    }
    return jwt.encode(payload, key, algorithm="RS256", headers={"kid": "key-c1"})


@requires(scope="academics.read")
async def protected_reader(record_id: str = "default") -> dict[str, Any]:
    """Read protected user records."""
    return ok(
        spoken_summary=f"Read record {record_id}",
        data={"record_id": record_id},
        module="protected_test",
        version="0.1.0",
    )


class MockProtectedModule:
    """Module containing both protected and anonymous tools for testing."""

    @property
    def name(self) -> str:
        return "protected_test"

    @property
    def version(self) -> str:
        return "0.1.0"

    def register_tools(self, mcp: Any, deps: Deps) -> None:
        tool_decorator = getattr(mcp, "tool", None)
        if callable(tool_decorator):
            tool_decorator(
                name="protected_reader",
                description=(
                    "Read protected user records. "
                    "Use when reading user progress, e.g. 'check my progress'. "
                    "Do not use for public actions."
                ),
            )(protected_reader)

    def register_jobs(self, worker: Any) -> None:
        return None

    def migrations_path(self) -> str | None:
        return None

    def health(self) -> HealthStatus:
        return HealthStatus(healthy=True, detail="")

    def on_event(self, event: Any) -> None:
        return None

    def export_user_data(self, user_id: str) -> dict[str, Any]:
        return {}

    def delete_user_data(self, user_id: str) -> None:
        return None


@pytest.mark.asyncio
async def test_rfc9728_protected_resource_metadata() -> None:
    """/.well-known/oauth-protected-resource returns valid metadata per ADR 0003."""
    app = create_app(enable_mcp=False)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        res = await client.get("/.well-known/oauth-protected-resource")
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("application/json")
        # ADR 0003: no WWW-Authenticate
        assert "WWW-Authenticate" not in res.headers

        data = res.json()
        assert "resource" in data
        assert "authorization_servers" in data
        assert "scopes_supported" in data
        assert "academics.read" in data["scopes_supported"]
        assert data["bearer_methods_supported"] == ["header"]


@pytest.mark.asyncio
async def test_invalid_token_returns_401_without_www_authenticate(
    auth_test_rsa_key: rsa.RSAPrivateKey,
) -> None:
    """Invalid token produces 401 without WWW-Authenticate header per ADR 0003."""
    jwk_dict = dict(json.loads(RSAAlgorithm.to_jwk(auth_test_rsa_key.public_key())))
    jwk_dict["kid"] = "key-c1"
    jwks = {"keys": [jwk_dict]}

    transport_mock = httpx.MockTransport(lambda _: httpx.Response(200, json=jwks))
    async with httpx.AsyncClient(transport=transport_mock) as http_client:
        validator = JWTValidator(
            issuer="https://auth.example.com",
            audience="sahayak-api",
            jwks_url="https://auth.example.com/.well-known/jwks.json",
            http_client=http_client,
        )
        app = create_app(enable_mcp=False, jwt_validator=validator)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            bad_headers = {"Authorization": "Bearer not-a-valid-token"}
            res = await client.get("/healthz", headers=bad_headers)
            assert res.status_code == 401
            assert "WWW-Authenticate" not in res.headers


@pytest.mark.asyncio
async def test_tool_authorization_e2e(auth_test_rsa_key: rsa.RSAPrivateKey) -> None:
    """Verify protected tool behavior without token, with wrong scope, and with valid token."""
    jwk_dict = dict(json.loads(RSAAlgorithm.to_jwk(auth_test_rsa_key.public_key())))
    jwk_dict["kid"] = "key-c1"
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
        registry.register(MockProtectedModule())
        registry.load(("_template",))

        app = create_app(registry=registry, jwt_validator=validator)

        asgi_transport = httpx.ASGITransport(app=app)

        async with app.router.lifespan_context(app):
            # 1. Anonymous caller calls anonymous tool (ping_echo) -> succeeds
            async with (
                httpx.AsyncClient(transport=asgi_transport, base_url="http://testserver") as client,
                streamable_http_client("http://testserver/mcp", http_client=cast(Any, client)) as (
                    r1,
                    w1,
                ),
                ClientSession(r1, w1) as session1,
            ):
                await session1.initialize()
                res = await session1.call_tool("ping_echo", arguments={"message": "hi"})
                assert not res.is_error
                data = json.loads(getattr(res.content[0], "text", "{}"))
                assert data["ok"] is True

            # 2. Anonymous caller calls protected tool -> auth_required
            async with (
                httpx.AsyncClient(transport=asgi_transport, base_url="http://testserver") as client,
                streamable_http_client("http://testserver/mcp", http_client=cast(Any, client)) as (
                    r2,
                    w2,
                ),
                ClientSession(r2, w2) as session2,
            ):
                await session2.initialize()
                res = await session2.call_tool("protected_reader", arguments={"record_id": "1"})
                data = json.loads(getattr(res.content[0], "text", "{}"))
                assert data["ok"] is False
                assert data["error_code"] == "auth_required"

            # 3. Authenticated caller missing academics.read scope -> forbidden
            token_wrong_scope = make_auth_token(auth_test_rsa_key, scope="other.scope")
            headers_wrong = {"Authorization": f"Bearer {token_wrong_scope}"}

            async with (
                httpx.AsyncClient(
                    transport=asgi_transport, base_url="http://testserver", headers=headers_wrong
                ) as client,
                streamable_http_client("http://testserver/mcp", http_client=cast(Any, client)) as (
                    r3,
                    w3,
                ),
                ClientSession(r3, w3) as session3,
            ):
                await session3.initialize()
                res = await session3.call_tool("protected_reader", arguments={"record_id": "2"})
                data = json.loads(getattr(res.content[0], "text", "{}"))
                assert data["ok"] is False
                assert data["error_code"] == "forbidden"

            # 4. Authenticated caller with academics.read scope -> succeeds
            token_valid = make_auth_token(auth_test_rsa_key, scope="academics.read")
            headers_valid = {"Authorization": f"Bearer {token_valid}"}

            async with (
                httpx.AsyncClient(
                    transport=asgi_transport, base_url="http://testserver", headers=headers_valid
                ) as client,
                streamable_http_client("http://testserver/mcp", http_client=cast(Any, client)) as (
                    r4,
                    w4,
                ),
                ClientSession(r4, w4) as session4,
            ):
                await session4.initialize()
                res = await session4.call_tool("protected_reader", arguments={"record_id": "42"})
                data = json.loads(getattr(res.content[0], "text", "{}"))
                assert data["ok"] is True
                assert data["data"]["record_id"] == "42"
