"""Contract tests for chores MCP tool over Streamable HTTP (T9.3)."""

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
from sahayak.modules.home.service.chores import ChoreService
from sahayak.modules.home.tools.chores import set_chore_service
from sahayak.shared.users.models import User


@pytest.fixture(scope="module")
def chores_contract_rsa_key() -> rsa.RSAPrivateKey:
    """RSA private key for signing test JWTs."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def make_test_token(
    key: rsa.RSAPrivateKey,
    *,
    sub: str,
    scope: str = "",
) -> str:
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
async def test_chores_contract_full_lifecycle(
    chores_contract_rsa_key: rsa.RSAPrivateKey,
) -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    jwk_dict = dict(json.loads(RSAAlgorithm.to_jwk(chores_contract_rsa_key.public_key())))
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
    registry.load(("home",))
    deps = Deps(session_factory=session_factory)
    app = create_app(
        registry=registry,
        deps=deps,
        jwt_validator=validator,
    )

    chore_service = ChoreService(session_factory=session_factory)
    set_chore_service(chore_service)

    user_id = uuid.uuid4()
    async with UnitOfWork(session_factory) as uow:
        uow.session.add(User(id=user_id))
        await uow.session.commit()

    token = make_test_token(chores_contract_rsa_key, sub=str(user_id))
    headers = {"Authorization": f"Bearer {token}"}
    asgi_transport = httpx.ASGITransport(app=app)

    try:
        async with app.router.lifespan_context(app):
            # 1. Anonymous call must fail
            async with (
                httpx.AsyncClient(
                    transport=asgi_transport, base_url="http://testserver"
                ) as anon_client,
                streamable_http_client(
                    "http://testserver/mcp", http_client=cast(Any, anon_client)
                ) as (r_anon, w_anon),
                ClientSession(r_anon, w_anon) as anon_session,
            ):
                await anon_session.initialize()
                anon_res = await anon_session.call_tool("chores", {"action": "list"})
                anon_data = json.loads(getattr(anon_res.content[0], "text", "{}"))
                assert anon_data.get("ok") is False
                assert anon_data.get("error_code") == "auth_required"

            # 2. Authenticated tool invocations
            async with (
                httpx.AsyncClient(
                    transport=asgi_transport,
                    base_url="http://testserver",
                    headers=headers,
                ) as auth_client,
                streamable_http_client(
                    "http://testserver/mcp", http_client=cast(Any, auth_client)
                ) as (r_auth, w_auth),
                ClientSession(r_auth, w_auth) as auth_session,
            ):
                await auth_session.initialize()

                # List tools verification
                tools_list = await auth_session.list_tools()
                chores_def = next((t for t in tools_list.tools if t.name == "chores"), None)
                assert chores_def is not None

                # Add chore
                res_add = await auth_session.call_tool(
                    "chores",
                    {"action": "add", "title": "Take out recycling", "frequency": "weekly"},
                )
                data_add = json.loads(getattr(res_add.content[0], "text", "{}"))
                assert data_add.get("ok") is True
                chore_data = data_add.get("data", {}).get("chore", {})
                assert chore_data.get("title") == "Take Out Recycling"

                # Assign rotation members
                res_assign = await auth_session.call_tool(
                    "chores",
                    {
                        "action": "assign",
                        "title": "Take out recycling",
                        "rotation_members": ["Sam", "Taylor"],
                    },
                )
                data_assign = json.loads(getattr(res_assign.content[0], "text", "{}"))
                assert data_assign.get("ok") is True

                # Whose turn
                res_turn = await auth_session.call_tool(
                    "chores",
                    {"action": "whose_turn", "title": "Take out recycling"},
                )
                data_turn = json.loads(getattr(res_turn.content[0], "text", "{}"))
                assert data_turn.get("ok") is True
                assert "Sam" in data_turn.get("spoken_summary", "")

                # Complete chore
                res_comp = await auth_session.call_tool(
                    "chores",
                    {"action": "complete", "title": "Take out recycling"},
                )
                data_comp = json.loads(getattr(res_comp.content[0], "text", "{}"))
                assert data_comp.get("ok") is True
                assert "Taylor" in data_comp.get("spoken_summary", "")

                # List chores
                res_list = await auth_session.call_tool("chores", {"action": "list"})
                data_list = json.loads(getattr(res_list.content[0], "text", "{}"))
                assert data_list.get("ok") is True
                assert len(data_list.get("data", {}).get("chores", [])) >= 1

    finally:
        await engine.dispose()
