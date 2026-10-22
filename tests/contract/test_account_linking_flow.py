"""Contract tests simulating OAuth 2.1 authorization code + PKCE account linking (T1.7)."""

from __future__ import annotations

import base64
import hashlib
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
def idp_rsa_key() -> rsa.RSAPrivateKey:
    """Generate RSA key pair representing the Cognito/Auth0 IdP."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@requires(scope="academics.read")
async def read_study_record(record_id: str = "default") -> dict[str, Any]:
    """Protected study tool."""
    return ok(spoken_summary=f"Record {record_id}", data={"record_id": record_id})


class MockAcademicsModule:
    """Mock academics module providing protected tool."""

    @property
    def name(self) -> str:
        return "academics"

    @property
    def version(self) -> str:
        return "0.1.0"

    def register_tools(self, mcp: Any, deps: Deps) -> None:
        tool_decorator = getattr(mcp, "tool", None)
        if callable(tool_decorator):
            tool_decorator(
                name="read_study_record",
                description=(
                    "Read protected record. Use when checking study progress. Do not use for other."
                ),
            )(read_study_record)

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
async def test_oauth21_pkce_account_linking_token_accepted_by_sahayak(
    idp_rsa_key: rsa.RSAPrivateKey,
) -> None:
    """OAuth 2.1 code exchange with PKCE yields an IdP token accepted by Sahayak."""
    # 1. Setup PKCE
    code_verifier = "a" * 43
    challenge_bytes = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(challenge_bytes).decode("ascii").rstrip("=")
    assert len(code_challenge) > 20

    # 2. Setup IdP mock JWKS
    jwk_dict = dict(json.loads(RSAAlgorithm.to_jwk(idp_rsa_key.public_key())))
    jwk_dict["kid"] = "cognito-key-1"
    jwks = {"keys": [jwk_dict]}

    issuer = "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_TestPool"
    audience = "sahayak-api"

    # 3. Simulate IdP Token endpoint response following authorization code exchange
    now = int(time.time())
    idp_token_payload = {
        "sub": "user-cognito-12345",
        "iss": issuer,
        "aud": audience,
        "client_id": "alexa-client-id-abc",
        "scope": "openid email sahayak-api/academics.read",
        "exp": now + 3600,
        "iat": now,
        "nbf": now,
        "token_use": "access",
    }
    access_token = jwt.encode(
        idp_token_payload,
        idp_rsa_key,
        algorithm="RS256",
        headers={"kid": "cognito-key-1"},
    )

    # 4. Initialize Sahayak with the IdP validator
    transport_mock = httpx.MockTransport(lambda _: httpx.Response(200, json=jwks))
    async with httpx.AsyncClient(transport=transport_mock) as http_client:
        validator = JWTValidator(
            issuer=issuer,
            audience=audience,
            jwks_url=f"{issuer}/.well-known/jwks.json",
            http_client=http_client,
        )

        registry = ModuleRegistry()
        registry.register(MockAcademicsModule())

        app = create_app(registry=registry, jwt_validator=validator)
        asgi_transport = httpx.ASGITransport(app=app)

        async with app.router.lifespan_context(app):
            # Test calling the protected tool using the IdP-issued access token
            headers = {"Authorization": f"Bearer {access_token}"}
            async with (
                httpx.AsyncClient(
                    transport=asgi_transport, base_url="http://testserver", headers=headers
                ) as client,
                streamable_http_client("http://testserver/mcp", http_client=cast(Any, client)) as (
                    r,
                    w,
                ),
                ClientSession(r, w) as session,
            ):
                await session.initialize()
                res = await session.call_tool(
                    "read_study_record", arguments={"record_id": "course-101"}
                )
                assert not res.is_error
                data = json.loads(getattr(res.content[0], "text", "{}"))
                assert data["ok"] is True
                assert data["data"]["record_id"] == "course-101"
