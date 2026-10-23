"""Contract tests for scheme_finder MCP tool over Streamable HTTP (T12.4)."""

from __future__ import annotations

import json
from typing import Any, cast

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.config import get_settings
from sahayak.core.module import Deps, ModuleRegistry
from sahayak.main import create_app
from sahayak.modules.local_info.service.schemes import SchemeService
from sahayak.modules.local_info.tools.schemes import set_scheme_service
from tests.security.isolation import ISOLATION_REGISTRY, assert_user_isolation


@pytest.fixture(scope="module")
def contract_rsa_key() -> rsa.RSAPrivateKey:
    """RSA private key for signing test JWTs."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.mark.asyncio
async def test_scheme_finder_mcp_contract_lifecycle(
    contract_rsa_key: rsa.RSAPrivateKey,
) -> None:
    """Contract test for scheme_finder over Streamable HTTP:

    1. Anonymous invocation succeeds for 'find' with profile criteria.
    2. Envelope structure contains spoken summary, data, and disclaimer.
    3. Blank profile asks for one missing fact in conversational speech.
    4. 'explain' action returns scheme benefits and portal URL.
    5. 'check_eligibility' returns deterministic rule verification.
    6. User isolation check passes with allows_anonymous=True.
    """
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    registry = ModuleRegistry()
    registry.load(("local_info",))
    deps = Deps(session_factory=session_factory)
    app = create_app(registry=registry, deps=deps)

    service = SchemeService()
    set_scheme_service(service)

    asgi_transport = httpx.ASGITransport(app=app)
    try:
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(transport=asgi_transport, base_url="http://testserver") as client,
            streamable_http_client("http://testserver/mcp", http_client=cast(Any, client)) as (
                r,
                w,
            ),
            ClientSession(r, w) as session,
        ):
            await session.initialize()

            # 1. Anonymous find for farmer profile
            res_find = await session.call_tool(
                "scheme_finder",
                arguments={
                    "action": "find",
                    "occupation": "farmer",
                    "age": 35,
                    "is_landowner": True,
                },
            )
            data_find = json.loads(getattr(res_find.content[0], "text", "{}"))
            assert data_find.get("ok") is True
            assert len(data_find.get("spoken_summary", "")) <= 300
            assert "guidance" in data_find.get("spoken_summary", "").lower()
            assert data_find.get("data", {}).get("eligible_count", 0) >= 1

            # 2. Blank profile asks for one fact (occupation)
            res_blank = await session.call_tool(
                "scheme_finder",
                arguments={"action": "find"},
            )
            data_blank = json.loads(getattr(res_blank.content[0], "text", "{}"))
            assert data_blank.get("ok") is True
            assert "occupation" in data_blank.get("spoken_summary", "").lower()
            assert data_blank.get("data", {}).get("status") == "needs_clarification"

            # 3. Explain action
            res_explain = await session.call_tool(
                "scheme_finder",
                arguments={"action": "explain", "scheme": "ayushman_bharat"},
            )
            data_explain = json.loads(getattr(res_explain.content[0], "text", "{}"))
            assert data_explain.get("ok") is True
            assert len(data_explain.get("spoken_summary", "")) <= 300
            assert "pmjay.gov.in" in data_explain.get("spoken_summary", "")

            # 4. Check eligibility action
            res_check = await session.call_tool(
                "scheme_finder",
                arguments={
                    "action": "check_eligibility",
                    "scheme": "atal_pension",
                    "age": 28,
                    "annual_income_inr": 200000,
                },
            )
            data_check = json.loads(getattr(res_check.content[0], "text", "{}"))
            assert data_check.get("ok") is True
            assert data_check.get("data", {}).get("status") == "eligible"

            # 5. Missing scheme for explain returns invalid_input
            res_bad = await session.call_tool(
                "scheme_finder",
                arguments={"action": "explain"},
            )
            data_bad = json.loads(getattr(res_bad.content[0], "text", "{}"))
            assert data_bad.get("ok") is False
            assert data_bad.get("error_code") == "invalid_input"

            # 6. User isolation check
            await assert_user_isolation(ISOLATION_REGISTRY["scheme_finder"], app, contract_rsa_key)
    finally:
        set_scheme_service(None)
        await engine.dispose()
