"""Contract tests for sales_summary MCP tool over Streamable HTTP (T10.3)."""

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
from sahayak.modules.business.service.sales import SalesService
from sahayak.modules.business.tools.orders import set_order_service
from sahayak.modules.business.tools.sales_summary import set_sales_service
from sahayak.shared.users.models import User


@pytest.fixture(scope="module")
def sales_contract_rsa_key() -> rsa.RSAPrivateKey:
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
async def test_sales_summary_contract_full_lifecycle(
    sales_contract_rsa_key: rsa.RSAPrivateKey,
) -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    jwk_dict = dict(json.loads(RSAAlgorithm.to_jwk(sales_contract_rsa_key.public_key())))
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

    order_svc = OrderService(session_factory=session_factory)
    set_order_service(order_svc)
    sales_svc = SalesService(session_factory=session_factory)
    set_sales_service(sales_svc)

    user_id = uuid.uuid4()
    async with UnitOfWork(session_factory) as uow:
        uow.session.add(User(id=user_id))
        await uow.session.commit()

    token = make_test_token(sales_contract_rsa_key, sub=str(user_id))
    headers = {"Authorization": f"Bearer {token}"}
    asgi_transport = httpx.ASGITransport(app=app)

    try:
        async with app.router.lifespan_context(app):
            # 1. Anonymous call fails
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
                anon_res = await anon_session.call_tool("sales_summary", {"action": "today"})
                anon_data = json.loads(getattr(anon_res.content[0], "text", "{}"))
                assert anon_data.get("ok") is False
                assert anon_data.get("error_code") == "auth_required"

            # 2. Authenticated lifecycle
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

                # Verify tool listed
                tools_list = await auth_session.list_tools()
                sales_def = next((t for t in tools_list.tools if t.name == "sales_summary"), None)
                assert sales_def is not None

                # Add product
                res_add = await auth_session.call_tool(
                    "sales_summary",
                    {
                        "action": "add_product",
                        "name": "Notebook",
                        "stock_level": 30,
                        "low_stock_threshold": 5,
                        "unit_price": 50.0,
                    },
                )
                data_add = json.loads(getattr(res_add.content[0], "text", "{}"))
                assert data_add.get("ok") is True
                assert data_add.get("data", {}).get("product", {}).get("stock_level") == 30
                assert "Product Notebook updated with 30 units" in data_add.get(
                    "spoken_summary", ""
                )

                # List products
                res_list = await auth_session.call_tool(
                    "sales_summary",
                    {"action": "list_products"},
                )
                data_list = json.loads(getattr(res_list.content[0], "text", "{}"))
                assert data_list.get("ok") is True
                assert data_list.get("data", {}).get("count") >= 1

                # Today sales
                res_today = await auth_session.call_tool(
                    "sales_summary",
                    {"action": "today"},
                )
                data_today = json.loads(getattr(res_today.content[0], "text", "{}"))
                assert data_today.get("ok") is True

                # Week sales
                res_week = await auth_session.call_tool(
                    "sales_summary",
                    {"action": "week"},
                )
                data_week = json.loads(getattr(res_week.content[0], "text", "{}"))
                assert data_week.get("ok") is True

                # Top products
                res_top = await auth_session.call_tool(
                    "sales_summary",
                    {"action": "top_products"},
                )
                data_top = json.loads(getattr(res_top.content[0], "text", "{}"))
                assert data_top.get("ok") is True

                # Low stock
                res_low = await auth_session.call_tool(
                    "sales_summary",
                    {"action": "low_stock"},
                )
                data_low = json.loads(getattr(res_low.content[0], "text", "{}"))
                assert data_low.get("ok") is True
    finally:
        await engine.dispose()
