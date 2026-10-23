"""Contract tests for finance_report MCP tool over Streamable HTTP (T6.4)."""

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
from sahayak.modules.finance.service.reports import FinanceReportService
from sahayak.modules.finance.tools.finance_report import set_finance_report_service
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
async def test_finance_report_mcp_contract_full_lifecycle(
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
    app = create_app(
        registry=registry,
        deps=deps,
        jwt_validator=validator,
    )

    # Initialize service
    report_service = FinanceReportService(session_factory=session_factory)
    set_finance_report_service(report_service)

    user_a = uuid.uuid4()
    async with UnitOfWork(session_factory) as uow:
        uow.session.add(User(id=user_a))
        await uow.session.flush()

    token_a = make_test_token(contract_rsa_key, sub=str(user_a))
    headers_a = {"Authorization": f"Bearer {token_a}"}

    asgi_transport = httpx.ASGITransport(app=app)

    try:
        async with app.router.lifespan_context(app):
            # 1. Anonymous call must be rejected with auth_required
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
                    "finance_report", arguments={"action": "summary"}
                )
                raw_anon = json.loads(getattr(res_anon.content[0], "text", "{}"))
                assert raw_anon.get("ok") is False
                assert raw_anon.get("error_code") == "auth_required"

            # 2. Authenticated user lifecycle
            async with (
                httpx.AsyncClient(
                    transport=asgi_transport, base_url="http://testserver", headers=headers_a
                ) as client,
                streamable_http_client("http://testserver/mcp", http_client=cast(Any, client)) as (
                    r_auth,
                    w_auth,
                ),
                ClientSession(r_auth, w_auth) as session_auth,
            ):
                await session_auth.initialize()

                # A. Add a bill
                res_add = await session_auth.call_tool(
                    "finance_report",
                    arguments={
                        "action": "add_bill",
                        "bill_name": "Wifi Subscription",
                        "amount": 1000,
                        "due_day": 12,
                    },
                )
                raw_add = json.loads(getattr(res_add.content[0], "text", "{}"))
                assert raw_add.get("ok") is True
                bill_id = raw_add.get("data", {}).get("bill", {}).get("id")
                assert bill_id is not None
                spoken_add = raw_add.get("spoken_summary", "")
                assert "Wifi Subscription" in spoken_add
                assert len(spoken_add) <= 300

                # B. Check bills due
                res_due = await session_auth.call_tool(
                    "finance_report",
                    arguments={
                        "action": "bills_due",
                        "due_days_ahead": 35,
                    },
                )
                raw_due = json.loads(getattr(res_due.content[0], "text", "{}"))
                assert raw_due.get("ok") is True
                assert raw_due.get("data", {}).get("count") == 1

                # C. Summary report
                res_sum = await session_auth.call_tool(
                    "finance_report",
                    arguments={
                        "action": "summary",
                        "period": "monthly",
                    },
                )
                raw_sum = json.loads(getattr(res_sum.content[0], "text", "{}"))
                assert raw_sum.get("ok") is True
                assert len(raw_sum.get("spoken_summary", "")) <= 300

                # D. Mark bill paid
                res_pay = await session_auth.call_tool(
                    "finance_report",
                    arguments={
                        "action": "mark_bill_paid",
                        "bill_id": bill_id,
                    },
                )
                raw_pay = json.loads(getattr(res_pay.content[0], "text", "{}"))
                assert raw_pay.get("ok") is True
                assert "paid" in raw_pay.get("spoken_summary", "").lower()

    finally:
        await jwks_client.aclose()
        await engine.dispose()
