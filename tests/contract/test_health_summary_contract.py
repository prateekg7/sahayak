"""Contract tests for health_summary MCP tool over Streamable HTTP (T7.2)."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, cast

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.auth.jwt import JWTValidator
from sahayak.core.config import get_settings
from sahayak.core.db.session import UnitOfWork
from sahayak.core.module import Deps, ModuleRegistry
from sahayak.main import create_app
from sahayak.modules.health.service.health_summary import HealthSummaryService
from sahayak.modules.health.tools.health_summary import set_health_summary_service
from sahayak.shared.users.models import User


@pytest.fixture(scope="module")
def contract_rsa_key() -> rsa.RSAPrivateKey:
    """RSA private key for signing test JWTs."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def make_test_token(
    key: rsa.RSAPrivateKey,
    *,
    sub: str,
    scope: str = "health.read health.write",
) -> str:
    """Generate a signed test JWT for MCP contract testing."""
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
    return jwt.encode(payload, key, algorithm="RS256", headers={"kid": "sec-test-key"})


@pytest.mark.asyncio
async def test_health_summary_mcp_contract_full_lifecycle(
    contract_rsa_key: rsa.RSAPrivateKey,
) -> None:
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
    registry.load(("academics", "productivity", "finance", "health"))
    deps = Deps(session_factory=session_factory)
    app = create_app(
        registry=registry,
        deps=deps,
        jwt_validator=validator,
    )

    summary_service = HealthSummaryService(session_factory=session_factory)
    set_health_summary_service(summary_service)

    user_a = uuid.uuid4()
    async with UnitOfWork(session_factory) as uow:
        uow.session.add(User(id=user_a))
        await uow.session.flush()

    token_a = make_test_token(contract_rsa_key, sub=str(user_a))
    headers_a = {"Authorization": f"Bearer {token_a}"}

    asgi_transport = httpx.ASGITransport(app=app)

    try:
        async with app.router.lifespan_context(app):
            # 1. Anonymous call rejected with auth_required
            async with (
                httpx.AsyncClient(transport=asgi_transport, base_url="http://testserver") as client,
                streamable_http_client("http://testserver/mcp", http_client=cast(Any, client)) as (
                    r_anon,
                    w_anon,
                ),
                ClientSession(r_anon, w_anon) as session_anon,
            ):
                await session_anon.initialize()
                res_anon = await session_anon.call_tool(
                    "health_summary", arguments={"action": "today"}
                )
                raw_anon = json.loads(getattr(res_anon.content[0], "text", "{}"))
                assert raw_anon.get("ok") is False
                assert raw_anon.get("error_code") == "auth_required"

            # 2. Authenticated user lifecycle
            async with (
                httpx.AsyncClient(
                    transport=asgi_transport, base_url="http://testserver", headers=headers_a
                ) as client_a,
                streamable_http_client(
                    "http://testserver/mcp", http_client=cast(Any, client_a)
                ) as (
                    ra,
                    wa,
                ),
                ClientSession(ra, wa) as session_a,
            ):
                await session_a.initialize()

                # 2a. Today summary initially
                res_init = await session_a.call_tool(
                    "health_summary",
                    {"action": "today"},
                )
                raw_init = json.loads(getattr(res_init.content[0], "text", "{}"))
                assert raw_init.get("ok") is True
                assert "disclaimer" in raw_init.get("data", {})

                # 2b. Add medicine
                res_add = await session_a.call_tool(
                    "health_summary",
                    {
                        "action": "add_medicine",
                        "medicine_name": "Multivitamin",
                        "times": ["08:00"],
                    },
                )
                raw_add = json.loads(getattr(res_add.content[0], "text", "{}"))
                assert raw_add.get("ok") is True
                assert "Added Multivitamin" in raw_add.get("spoken_summary", "")

                # 2c. Medicines due
                res_due = await session_a.call_tool(
                    "health_summary",
                    {"action": "medicines_due"},
                )
                raw_due = json.loads(getattr(res_due.content[0], "text", "{}"))
                assert raw_due.get("ok") is True
                assert "Multivitamin" in raw_due.get("spoken_summary", "")

                # 2d. Mark taken
                res_mark = await session_a.call_tool(
                    "health_summary",
                    {
                        "action": "mark_taken",
                        "medicine_name": "Multivitamin",
                        "scheduled_time": "08:00",
                    },
                )
                raw_mark = json.loads(getattr(res_mark.content[0], "text", "{}"))
                assert raw_mark.get("ok") is True
                assert "Marked your Multivitamin" in raw_mark.get("spoken_summary", "")

                # 2e. Weekly summary
                res_week = await session_a.call_tool(
                    "health_summary",
                    {"action": "week"},
                )
                raw_week = json.loads(getattr(res_week.content[0], "text", "{}"))
                assert raw_week.get("ok") is True
                assert "Past 7 days" in raw_week.get("spoken_summary", "")

    finally:
        await engine.dispose()
