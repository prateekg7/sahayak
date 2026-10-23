"""Contract tests for pantry_recipes MCP tool over Streamable HTTP (T9.3)."""

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
from sahayak.modules.home.service.pantry import PantryService
from sahayak.modules.home.tools.pantry_recipes import set_pantry_service
from sahayak.modules.home.tools.shared_list import set_shared_list_service
from sahayak.shared.users.models import User


@pytest.fixture(scope="module")
def pantry_contract_rsa_key() -> rsa.RSAPrivateKey:
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
async def test_pantry_recipes_contract_full_lifecycle(
    pantry_contract_rsa_key: rsa.RSAPrivateKey,
) -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    jwk_dict = dict(json.loads(RSAAlgorithm.to_jwk(pantry_contract_rsa_key.public_key())))
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

    pantry_service = PantryService(session_factory=session_factory, list_service=list_service)
    set_pantry_service(pantry_service)

    user_id = uuid.uuid4()
    async with UnitOfWork(session_factory) as uow:
        uow.session.add(User(id=user_id))
        await uow.session.commit()

    token = make_test_token(pantry_contract_rsa_key, sub=str(user_id))
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
                anon_res = await anon_session.call_tool("pantry_recipes", {"action": "pantry_list"})
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
                pantry_def = next((t for t in tools_list.tools if t.name == "pantry_recipes"), None)
                assert pantry_def is not None

                # Add pantry items
                res_add1 = await auth_session.call_tool(
                    "pantry_recipes",
                    {"action": "pantry_add", "item": "Pasta", "quantity": "500 g"},
                )
                data_add1 = json.loads(getattr(res_add1.content[0], "text", "{}"))
                assert data_add1.get("ok") is True
                assert len(data_add1.get("spoken_summary", "")) <= 300

                res_add2 = await auth_session.call_tool(
                    "pantry_recipes",
                    {"action": "pantry_add", "item": "Garlic", "quantity": "1 head"},
                )
                data_add2 = json.loads(getattr(res_add2.content[0], "text", "{}"))
                assert data_add2.get("ok") is True

                # List pantry
                res_list = await auth_session.call_tool("pantry_recipes", {"action": "pantry_list"})
                data_list = json.loads(getattr(res_list.content[0], "text", "{}"))
                assert data_list.get("ok") is True
                assert len(data_list.get("data", {}).get("items", [])) >= 2

                # Set preferences
                res_pref = await auth_session.call_tool(
                    "pantry_recipes",
                    {
                        "action": "set_preferences",
                        "diet": "vegetarian",
                        "allergies": ["shellfish"],
                    },
                )
                data_pref = json.loads(getattr(res_pref.content[0], "text", "{}"))
                assert data_pref.get("ok") is True

                # Suggest recipes with add_missing_to_shopping_list
                res_sug = await auth_session.call_tool(
                    "pantry_recipes",
                    {
                        "action": "suggest_recipes",
                        "add_missing_to_shopping_list": True,
                    },
                )
                data_sug = json.loads(getattr(res_sug.content[0], "text", "{}"))
                assert data_sug.get("ok") is True
                assert len(data_sug.get("data", {}).get("recipes", [])) >= 1

                # Meal plan
                res_plan = await auth_session.call_tool(
                    "pantry_recipes",
                    {"action": "meal_plan", "days": 2},
                )
                data_plan = json.loads(getattr(res_plan.content[0], "text", "{}"))
                assert data_plan.get("ok") is True
                assert len(data_plan.get("data", {}).get("plan", [])) == 2

    finally:
        await engine.dispose()
