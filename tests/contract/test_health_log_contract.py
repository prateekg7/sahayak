"""Contract tests for health_log MCP tool over Streamable HTTP (T7.1)."""

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
from sahayak.modules.health.service.health_log import HealthLogService
from sahayak.modules.health.tools.health_log import set_health_log_service
from sahayak.shared.users.models import User


@pytest.fixture(scope="module")
def contract_rsa_key() -> rsa.RSAPrivateKey:
    """RSA private key for signing test JWTs."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def make_test_token(
    key: rsa.RSAPrivateKey,
    *,
    sub: str,
    scope: str = "health.write",
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
async def test_health_log_mcp_contract_full_lifecycle(
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

    health_service = HealthLogService(session_factory=session_factory)
    set_health_log_service(health_service)

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
                    "health_log", arguments={"action": "log", "kind": "water", "value": 500}
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

                # 2a. Reject absurd water value (plausibility check)
                res_absurd = await session_a.call_tool(
                    "health_log",
                    {"action": "log", "kind": "water", "value": 10000, "unit": "ml"},
                )
                raw_absurd = json.loads(getattr(res_absurd.content[0], "text", "{}"))
                assert raw_absurd.get("ok") is False
                assert raw_absurd.get("error_code") == "invalid_input"
                assert "plausible amount" in raw_absurd.get("spoken_summary", "")

                # 2b. Log 500 ml water
                res_water = await session_a.call_tool(
                    "health_log",
                    {"action": "log", "kind": "water", "value": 500, "unit": "ml"},
                )
                raw_water = json.loads(getattr(res_water.content[0], "text", "{}"))
                assert raw_water.get("ok") is True
                assert "Logged 500 ml of water" in raw_water.get("spoken_summary", "")
                assert "disclaimer" in raw_water.get("data", {})

                # 2c. Log meal
                res_meal = await session_a.call_tool(
                    "health_log",
                    {
                        "action": "log",
                        "kind": "meal",
                        "meal_name": "Greek yogurt with honey",
                        "meal_type": "breakfast",
                        "calories": 250,
                    },
                )
                raw_meal = json.loads(getattr(res_meal.content[0], "text", "{}"))
                assert raw_meal.get("ok") is True
                assert "Logged breakfast: Greek yogurt" in raw_meal.get("spoken_summary", "")

                # 2d. Log workout
                res_wo = await session_a.call_tool(
                    "health_log",
                    {
                        "action": "log",
                        "kind": "workout",
                        "activity": "Evening walk",
                        "duration": 30,
                        "unit": "minutes",
                    },
                )
                raw_wo = json.loads(getattr(res_wo.content[0], "text", "{}"))
                assert raw_wo.get("ok") is True
                assert "Logged 30 minutes of Evening walk" in raw_wo.get("spoken_summary", "")

                # 2e. List water entries
                res_list = await session_a.call_tool(
                    "health_log",
                    {"action": "list", "kind": "water"},
                )
                raw_list = json.loads(getattr(res_list.content[0], "text", "{}"))
                assert raw_list.get("ok") is True
                assert raw_list.get("data", {}).get("count") >= 1

                # 2f. Undo last water entry
                res_undo = await session_a.call_tool(
                    "health_log",
                    {"action": "undo_last", "kind": "water"},
                )
                raw_undo = json.loads(getattr(res_undo.content[0], "text", "{}"))
                assert raw_undo.get("ok") is True
                assert "Undid your last water log" in raw_undo.get("spoken_summary", "")

    finally:
        await engine.dispose()
