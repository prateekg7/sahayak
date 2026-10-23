"""Contract tests for orders MCP tool over Streamable HTTP (T10.1)."""

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
from sahayak.modules.business.service.orders import OrderService
from sahayak.modules.business.tools.orders import set_order_service
from sahayak.shared.users.models import User


@pytest.fixture(scope="module")
def orders_contract_rsa_key() -> rsa.RSAPrivateKey:
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
async def test_orders_contract_full_lifecycle(
    orders_contract_rsa_key: rsa.RSAPrivateKey,
) -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    jwk_dict = dict(json.loads(RSAAlgorithm.to_jwk(orders_contract_rsa_key.public_key())))
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
    registry.load(("business",))
    deps = Deps(session_factory=session_factory)
    app = create_app(
        registry=registry,
        deps=deps,
        jwt_validator=validator,
    )

    order_service = OrderService(session_factory=session_factory)
    set_order_service(order_service)

    user_id = uuid.uuid4()
    async with UnitOfWork(session_factory) as uow:
        uow.session.add(User(id=user_id))
        await uow.session.commit()

    token = make_test_token(orders_contract_rsa_key, sub=str(user_id))
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
                anon_res = await anon_session.call_tool("orders", {"action": "list_pending"})
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
                orders_def = next((t for t in tools_list.tools if t.name == "orders"), None)
                assert orders_def is not None

                # Create order
                res_create = await auth_session.call_tool(
                    "orders",
                    {
                        "action": "create",
                        "customer_name": "Ramesh",
                        "items": [
                            {"item_name": "Calculator", "quantity": 1, "unit_price": 500.0},
                            {"item_name": "Battery", "quantity": 2, "unit_price": 25.0},
                        ],
                    },
                )
                data_create = json.loads(getattr(res_create.content[0], "text", "{}"))
                assert data_create.get("ok") is True
                assert len(data_create.get("spoken_summary", "")) <= 300
                order_num = data_create.get("data", {}).get("order", {}).get("order_number")
                assert order_num is not None

                # List pending
                res_list = await auth_session.call_tool("orders", {"action": "list_pending"})
                data_list = json.loads(getattr(res_list.content[0], "text", "{}"))
                assert data_list.get("ok") is True
                assert len(data_list.get("data", {}).get("orders", [])) >= 1

                # Get order details
                res_get = await auth_session.call_tool(
                    "orders",
                    {"action": "get", "order_number": order_num},
                )
                data_get = json.loads(getattr(res_get.content[0], "text", "{}"))
                assert data_get.get("ok") is True
                assert "Calculator" in data_get.get("spoken_summary", "")

                # Update status: pending -> packed
                res_upd = await auth_session.call_tool(
                    "orders",
                    {"action": "update_status", "order_number": order_num, "status": "packed"},
                )
                data_upd = json.loads(getattr(res_upd.content[0], "text", "{}"))
                assert data_upd.get("ok") is True
                assert "packed" in data_upd.get("spoken_summary", "")

                # Illegal status transition: packed -> pending
                res_illegal = await auth_session.call_tool(
                    "orders",
                    {"action": "update_status", "order_number": order_num, "status": "pending"},
                )
                data_illegal = json.loads(getattr(res_illegal.content[0], "text", "{}"))
                assert data_illegal.get("ok") is False
                assert data_illegal.get("error_code") == "invalid_input"

    finally:
        await engine.dispose()
