"""Contract tests for shared_list MCP tool over Streamable HTTP (T9.2)."""

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
from sahayak.modules.home.service.lists import SharedListService
from sahayak.modules.home.tools.shared_list import set_shared_list_service
from sahayak.shared.users.models import User


@pytest.fixture(scope="module")
def home_contract_rsa_key() -> rsa.RSAPrivateKey:
    """RSA private key for signing test JWTs."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def make_test_token(
    key: rsa.RSAPrivateKey,
    *,
    sub: str,
    scope: str = "",
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
async def test_shared_list_contract_anonymous_and_authenticated_lifecycle(
    home_contract_rsa_key: rsa.RSAPrivateKey,
) -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    jwk_dict = dict(json.loads(RSAAlgorithm.to_jwk(home_contract_rsa_key.public_key())))
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

    list_service = SharedListService(session_factory=session_factory)
    set_shared_list_service(list_service)

    user_id = uuid.uuid4()
    async with UnitOfWork(session_factory) as uow:
        uow.session.add(User(id=user_id))
        await uow.session.commit()

    token = make_test_token(home_contract_rsa_key, sub=str(user_id))
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
                anon_res = await anon_session.call_tool("shared_list", {"action": "read"})
                anon_data = json.loads(getattr(anon_res.content[0], "text", "{}"))
                assert anon_data.get("ok") is False
                assert anon_data.get("error_code") == "auth_required"

            # 2. Authenticated calls
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

                # Add item
                add_res = await auth_session.call_tool(
                    "shared_list",
                    {"action": "add", "item": "2 liters of whole milk", "list_name": "groceries"},
                )
                add_data = json.loads(getattr(add_res.content[0], "text", "{}"))
                assert add_data.get("ok") is True
                assert len(add_data.get("spoken_summary", "")) <= 300
                assert "Whole Milk" in add_data.get("spoken_summary", "")

                # Read list
                read_res = await auth_session.call_tool(
                    "shared_list",
                    {"action": "read", "list_name": "groceries"},
                )
                read_data = json.loads(getattr(read_res.content[0], "text", "{}"))
                assert read_data.get("ok") is True
                assert read_data.get("data", {}).get("total_items") == 1

                # Check off item
                check_res = await auth_session.call_tool(
                    "shared_list",
                    {"action": "check_off", "item": "whole milk", "list_name": "groceries"},
                )
                check_data = json.loads(getattr(check_res.content[0], "text", "{}"))
                assert check_data.get("ok") is True
                assert check_data.get("data", {}).get("item", {}).get("checked") is True

                # Clear checked
                clear_res = await auth_session.call_tool(
                    "shared_list",
                    {"action": "clear_checked", "list_name": "groceries"},
                )
                clear_data = json.loads(getattr(clear_res.content[0], "text", "{}"))
                assert clear_data.get("ok") is True
                assert clear_data.get("data", {}).get("cleared_count") == 1

                # Invalid action
                inv_res = await auth_session.call_tool(
                    "shared_list",
                    {"action": "fly_to_moon"},
                )
                inv_data = json.loads(getattr(inv_res.content[0], "text", "{}"))
                assert inv_data.get("ok") is False
                assert inv_data.get("error_code") == "invalid_input"
    finally:
        await engine.dispose()
