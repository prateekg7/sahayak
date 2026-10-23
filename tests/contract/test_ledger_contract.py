"""Contract tests for ledger MCP tool over Streamable HTTP (T10.2)."""

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
from sahayak.modules.business.service.ledger import LedgerService
from sahayak.modules.business.service.orders import OrderService
from sahayak.modules.business.tools.ledger import set_ledger_service
from sahayak.modules.business.tools.orders import set_order_service
from sahayak.shared.users.models import User


@pytest.fixture(scope="module")
def ledger_contract_rsa_key() -> rsa.RSAPrivateKey:
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
async def test_ledger_contract_full_lifecycle(
    ledger_contract_rsa_key: rsa.RSAPrivateKey,
) -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    jwk_dict = dict(json.loads(RSAAlgorithm.to_jwk(ledger_contract_rsa_key.public_key())))
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
    ledger_svc = LedgerService(session_factory=session_factory)
    set_ledger_service(ledger_svc)

    user_id = uuid.uuid4()
    async with UnitOfWork(session_factory) as uow:
        uow.session.add(User(id=user_id))
        await uow.session.commit()

    token = make_test_token(ledger_contract_rsa_key, sub=str(user_id))
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
                anon_res = await anon_session.call_tool("ledger", {"action": "top_dues"})
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
                ledger_def = next((t for t in tools_list.tools if t.name == "ledger"), None)
                assert ledger_def is not None

                # Add customer due
                res_due = await auth_session.call_tool(
                    "ledger",
                    {
                        "action": "add_due",
                        "customer_name": "Pooja",
                        "amount": 350.0,
                        "notes": "Cosmetics and shampoo",
                    },
                )
                data_due = json.loads(getattr(res_due.content[0], "text", "{}"))
                assert data_due.get("ok") is True
                assert data_due.get("data", {}).get("balance_minor") == 35000
                assert "Added due of 350 rupees for Pooja" in data_due.get("spoken_summary", "")

                # Record payment
                res_pay = await auth_session.call_tool(
                    "ledger",
                    {
                        "action": "record_payment",
                        "customer_name": "Pooja",
                        "amount": 150.0,
                    },
                )
                data_pay = json.loads(getattr(res_pay.content[0], "text", "{}"))
                assert data_pay.get("ok") is True
                assert data_pay.get("data", {}).get("balance_minor") == 20000

                # Check customer balance
                res_bal = await auth_session.call_tool(
                    "ledger",
                    {
                        "action": "balance",
                        "customer_name": "Pooja",
                    },
                )
                data_bal = json.loads(getattr(res_bal.content[0], "text", "{}"))
                assert data_bal.get("ok") is True
                assert data_bal.get("data", {}).get("balance_minor") == 20000
                assert "Pooja currently owes 200 rupees" in data_bal.get("spoken_summary", "")

                # Query top dues
                res_top = await auth_session.call_tool("ledger", {"action": "top_dues"})
                data_top = json.loads(getattr(res_top.content[0], "text", "{}"))
                assert data_top.get("ok") is True
                assert len(data_top.get("data", {}).get("top_dues", [])) >= 1

                # Daily reconciliation
                res_rec = await auth_session.call_tool("ledger", {"action": "reconcile"})
                data_rec = json.loads(getattr(res_rec.content[0], "text", "{}"))
                assert data_rec.get("ok") is True
                assert data_rec.get("data", {}).get("discrepancies_count") == 0
    finally:
        await engine.dispose()
