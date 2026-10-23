"""Contract tests for expense_log MCP tool over Streamable HTTP (T6.1)."""

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
from sahayak.modules.finance.service.expenses import ExpenseService
from sahayak.modules.finance.tools.expense_log import set_expense_service
from sahayak.shared.users.models import User


@pytest.fixture(scope="module")
def contract_rsa_key() -> rsa.RSAPrivateKey:
    """RSA private key for signing test JWTs."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def make_test_token(
    key: rsa.RSAPrivateKey,
    *,
    sub: str,
    scope: str = "finance.write",
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
async def test_expenses_mcp_contract_full_lifecycle_and_isolation(
    contract_rsa_key: rsa.RSAPrivateKey,
) -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    # Configure JWT validator with mock JWKS
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
    registry.load(("academics", "productivity", "finance"))

    deps = Deps(session_factory=session_factory)
    app = create_app(registry=registry, deps=deps, jwt_validator=validator)

    service = ExpenseService(session_factory=session_factory)
    set_expense_service(service)

    # Pre-seed users
    user_a_id = uuid.uuid4()
    user_b_id = uuid.uuid4()
    async with UnitOfWork(session_factory) as uow:
        uow.session.add(User(id=user_a_id))
        uow.session.add(User(id=user_b_id))
        await uow.session.flush()

    token_a = make_test_token(contract_rsa_key, sub=str(user_a_id))
    token_b = make_test_token(contract_rsa_key, sub=str(user_b_id))

    asgi_transport = httpx.ASGITransport(app=app)

    try:
        async with app.router.lifespan_context(app):
            # 1. Anonymous call rejected
            async with (
                httpx.AsyncClient(
                    transport=asgi_transport, base_url="http://testserver"
                ) as anon_client,
                streamable_http_client(
                    "http://testserver/mcp", http_client=cast(Any, anon_client)
                ) as (r, w),
                ClientSession(r, w) as anon_session,
            ):
                await anon_session.initialize()
                anon_res = await anon_session.call_tool("expense_log", arguments={"action": "list"})
                anon_data = json.loads(getattr(anon_res.content[0], "text", "{}"))
                assert anon_data.get("ok") is False
                assert anon_data.get("error_code") == "auth_required"

            # 2. User A lifecycle: add -> list -> undo_last
            headers_a = {"Authorization": f"Bearer {token_a}"}
            async with (
                httpx.AsyncClient(
                    transport=asgi_transport, base_url="http://testserver", headers=headers_a
                ) as client_a,
                streamable_http_client(
                    "http://testserver/mcp", http_client=cast(Any, client_a)
                ) as (ra, wa),
                ClientSession(ra, wa) as session_a,
            ):
                await session_a.initialize()

                # Add expense
                res_add = await session_a.call_tool(
                    "expense_log",
                    arguments={
                        "action": "add",
                        "amount": 200,
                        "currency": "INR",
                        "category": "groceries",
                        "note": "Almond milk and oats",
                    },
                )
                data_add = json.loads(getattr(res_add.content[0], "text", "{}"))
                assert data_add.get("ok") is True
                assert "Added 200 rupees for groceries." in data_add.get("spoken_summary", "")
                exp_id = data_add.get("data", {}).get("expense", {}).get("id")
                assert exp_id is not None

                # List expenses
                res_list = await session_a.call_tool(
                    "expense_log",
                    arguments={"action": "list"},
                )
                data_list = json.loads(getattr(res_list.content[0], "text", "{}"))
                assert data_list.get("ok") is True
                assert data_list.get("data", {}).get("count") == 1
                assert data_list.get("data", {}).get("total_amount_minor") == 20000

                # User B cannot see User A's expense
                headers_b = {"Authorization": f"Bearer {token_b}"}
                async with (
                    httpx.AsyncClient(
                        transport=asgi_transport,
                        base_url="http://testserver",
                        headers=headers_b,
                    ) as client_b,
                    streamable_http_client(
                        "http://testserver/mcp", http_client=cast(Any, client_b)
                    ) as (rb, wb),
                    ClientSession(rb, wb) as session_b,
                ):
                    await session_b.initialize()

                    res_b_list = await session_b.call_tool(
                        "expense_log",
                        arguments={"action": "list"},
                    )
                    data_b_list = json.loads(getattr(res_b_list.content[0], "text", "{}"))
                    assert data_b_list.get("ok") is True
                    assert data_b_list.get("data", {}).get("count") == 0

                    # User B cannot delete User A's expense
                    res_b_del = await session_b.call_tool(
                        "expense_log",
                        arguments={"action": "delete", "expense_id": exp_id},
                    )
                    data_b_del = json.loads(getattr(res_b_del.content[0], "text", "{}"))
                    assert data_b_del.get("ok") is False
                    assert data_b_del.get("error_code") == "not_found"

                # User A undoes last expense
                res_undo = await session_a.call_tool(
                    "expense_log",
                    arguments={"action": "undo_last"},
                )
                data_undo = json.loads(getattr(res_undo.content[0], "text", "{}"))
                assert data_undo.get("ok") is True
                assert "Undid your last expense" in data_undo.get("spoken_summary", "")

    finally:
        await engine.dispose()
