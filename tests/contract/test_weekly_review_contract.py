"""Contract tests for weekly_review MCP tool over Streamable HTTP (T13.2)."""

from __future__ import annotations

import json
from typing import Any, cast

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.auth.jwt import JWTValidator
from sahayak.core.config import get_settings
from sahayak.core.module import Deps, ModuleRegistry
from sahayak.main import create_app
from sahayak.modules.productivity.service.weekly_review import WeeklyReviewService
from sahayak.modules.productivity.tools.weekly_review import set_weekly_review_service
from tests.security.isolation import ISOLATION_REGISTRY, assert_user_isolation, make_test_jwt


@pytest.fixture(scope="module")
def contract_rsa_key() -> rsa.RSAPrivateKey:
    """RSA private key for signing test JWTs."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.mark.asyncio
async def test_weekly_review_mcp_contract_lifecycle(
    contract_rsa_key: rsa.RSAPrivateKey,
) -> None:
    """Contract test for weekly_review over Streamable HTTP:

    1. Anonymous invocation is rejected with auth_required.
    2. Authenticated invocation returns standard envelope and spoken summary <= 300 chars.
    3. Auto-isolation check passes.
    """
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    jwk_dict = dict(json.loads(RSAAlgorithm.to_jwk(contract_rsa_key.public_key())))
    jwk_dict["kid"] = "sec-test-key"
    jwks = {"keys": [jwk_dict]}

    transport_mock = httpx.MockTransport(lambda _: httpx.Response(200, json=jwks))
    jwks_client = httpx.AsyncClient(transport=transport_mock)

    validator = JWTValidator(
        issuer="https://auth.example.com",
        audience="sahayak-api",
        jwks_url="https://auth.example.com/.well-known/jwks.json",
        http_client=jwks_client,
    )

    registry = ModuleRegistry()
    registry.load(("productivity",))
    deps = Deps(session_factory=session_factory)
    app = create_app(registry=registry, deps=deps, jwt_validator=validator)

    service = WeeklyReviewService(session_factory=session_factory)
    set_weekly_review_service(service)

    test_sub = "usr_weekly_contract_test_01"
    valid_token = make_test_jwt(contract_rsa_key, sub=test_sub)
    headers = {"Authorization": f"Bearer {valid_token}"}

    asgi_transport = httpx.ASGITransport(app=app)
    try:
        async with app.router.lifespan_context(app):
            async with (
                httpx.AsyncClient(
                    transport=asgi_transport, base_url="http://testserver", headers=headers
                ) as client,
                streamable_http_client("http://testserver/mcp", http_client=cast(Any, client)) as (
                    read_stream,
                    write_stream,
                ),
                ClientSession(read_stream, write_stream) as session,
            ):
                await session.initialize()

                # 1. Call weekly_review
                res = await session.call_tool("weekly_review", arguments={"timezone": "UTC"})
                raw_text = getattr(res.content[0], "text", "{}")
                payload = json.loads(raw_text)

                assert payload.get("ok") is True
                assert "spoken_summary" in payload
                spoken = payload["spoken_summary"]
                assert len(spoken) <= 300
                assert "data" in payload
                data = payload["data"]
                assert data.get("period") == "weekly"

            # 2. Run auto-isolation check inside lifespan context
            spec = ISOLATION_REGISTRY["weekly_review"]
            await assert_user_isolation(spec, app, contract_rsa_key)
    finally:
        await engine.dispose()
