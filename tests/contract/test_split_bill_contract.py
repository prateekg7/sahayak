"""Contract tests for split_bill MCP tool over Streamable HTTP (T6.3)."""

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
from sahayak.modules.finance.service.split_bill import SplitBillService
from sahayak.modules.finance.tools.split_bill import set_split_bill_service
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
async def test_split_bill_mcp_contract_full_lifecycle_and_isolation(
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
    registry.load(("academics", "productivity", "finance"))

    deps = Deps(session_factory=session_factory)
    app = create_app(registry=registry, deps=deps, jwt_validator=validator)

    split_service = SplitBillService(session_factory=session_factory)
    set_split_bill_service(split_service)

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
            # 1. Anonymous rejection
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
                anon_res = await anon_session.call_tool(
                    "split_bill",
                    arguments={"action": "split", "amount": 1200, "participants": ["A", "B"]},
                )
                anon_data = json.loads(getattr(anon_res.content[0], "text", "{}"))
                assert anon_data.get("ok") is False
                assert anon_data.get("error_code") == "auth_required"

            # 2. User A lifecycle: split -> create_group -> balances -> settle
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

                # Standalone split
                res_split = await session_a.call_tool(
                    "split_bill",
                    arguments={
                        "action": "split",
                        "amount": 1200,
                        "participants": ["Alice", "Bob"],
                        "payer": "You",
                    },
                )
                data_split = json.loads(getattr(res_split.content[0], "text", "{}"))
                assert data_split.get("ok") is True
                assert "Split 1200 rupees among 3 people" in data_split.get("spoken_summary", "")

                # Create group Goa Trip
                res_grp = await session_a.call_tool(
                    "split_bill",
                    arguments={
                        "action": "create_group",
                        "group": "Goa Trip",
                        "participants": ["Alice", "Bob"],
                    },
                )
                data_grp = json.loads(getattr(res_grp.content[0], "text", "{}"))
                assert data_grp.get("ok") is True

                # Split in Goa Trip
                res_split_grp = await session_a.call_tool(
                    "split_bill",
                    arguments={
                        "action": "split",
                        "group": "Goa Trip",
                        "amount": 900,
                        "participants": ["You", "Alice", "Bob"],
                        "description": "Scuba diving",
                    },
                )
                data_split_grp = json.loads(getattr(res_split_grp.content[0], "text", "{}"))
                assert data_split_grp.get("ok") is True

                # Balances in Goa Trip
                res_bal = await session_a.call_tool(
                    "split_bill",
                    arguments={"action": "balances", "group": "Goa Trip"},
                )
                data_bal = json.loads(getattr(res_bal.content[0], "text", "{}"))
                assert data_bal.get("ok") is True

                # User B isolation check
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

                    # User B cannot see User A's balances
                    res_b_bal = await session_b.call_tool(
                        "split_bill",
                        arguments={"action": "balances", "group": "Goa Trip"},
                    )
                    data_b_bal = json.loads(getattr(res_b_bal.content[0], "text", "{}"))
                    assert data_b_bal.get("ok") is False
                    assert data_b_bal.get("error_code") == "not_found"

                    # User B cannot settle in User A's group
                    res_b_settle = await session_b.call_tool(
                        "split_bill",
                        arguments={
                            "action": "settle",
                            "group": "Goa Trip",
                            "settle_from": "Alice",
                            "settle_to": "You",
                            "amount": 300,
                        },
                    )
                    data_b_settle = json.loads(getattr(res_b_settle.content[0], "text", "{}"))
                    assert data_b_settle.get("ok") is False
                    assert data_b_settle.get("error_code") == "not_found"

                # Settle debt
                res_settle = await session_a.call_tool(
                    "split_bill",
                    arguments={
                        "action": "settle",
                        "group": "Goa Trip",
                        "settle_from": "Alice",
                        "settle_to": "You",
                        "amount": 300,
                    },
                )
                data_settle = json.loads(getattr(res_settle.content[0], "text", "{}"))
                assert data_settle.get("ok") is True
                assert "Recorded settlement" in data_settle.get("spoken_summary", "")

    finally:
        await engine.dispose()
