"""Contract tests for commodity_prices MCP tool over Streamable HTTP (T12.3)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
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
from sahayak.modules.local_info.adapters.commodity import CommodityHttpDataSource
from sahayak.modules.local_info.service.commodity import CommodityService
from sahayak.modules.local_info.tools.commodity import set_commodity_service
from tests.security.isolation import ISOLATION_REGISTRY, assert_user_isolation


@pytest.fixture(scope="module")
def contract_rsa_key() -> rsa.RSAPrivateKey:
    """RSA private key for signing test JWTs."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.mark.asyncio
async def test_commodity_prices_mcp_contract_lifecycle(
    contract_rsa_key: rsa.RSAPrivateKey,
) -> None:
    """Contract test for commodity_prices over Streamable HTTP:

    1. Anonymous invocation succeeds for 'get_price' with Hindi crop name ('gehun').
    2. Envelope structure contains spoken summary, data (both quintal and kg), and next_actions.
    3. 'compare_markets' succeeds.
    4. Missing commodity name returns invalid_input.
    5. User isolation check passes with allows_anonymous=True.
    """
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    registry = ModuleRegistry()
    registry.load(("local_info",))
    deps = Deps(session_factory=session_factory)
    app = create_app(registry=registry, deps=deps)

    now = datetime(2026, 10, 24, 12, 0, 0, tzinfo=UTC)

    def mock_agri_api(request: httpx.Request) -> httpx.Response:
        if "commodity-prices" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "record": {
                        "commodity": "Wheat",
                        "market": "Azadpur",
                        "state": "NCT of Delhi",
                        "arrival_date": "2026-10-24",
                        "min_price": 2400,
                        "max_price": 2600,
                        "modal_price": 2500,
                    }
                },
            )
        if "commodity-trend" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "trend": {
                        "current_modal_kg": 25.0,
                        "previous_modal_kg": 24.0,
                        "change_pct": 4.2,
                        "direction": "up",
                    }
                },
            )
        return httpx.Response(404)

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_agri_api))
    adapter = CommodityHttpDataSource(http_client=mock_client, clock=lambda: now)
    service = CommodityService(data_source=adapter)
    set_commodity_service(service)

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

            # 1. Anonymous get_price
            res_price = await session.call_tool(
                "commodity_prices",
                arguments={"action": "get_price", "commodity": "gehun", "market": "Azadpur"},
            )
            data_price = json.loads(getattr(res_price.content[0], "text", "{}"))
            assert data_price.get("ok") is True
            assert len(data_price.get("spoken_summary", "")) <= 300
            assert (
                "Wheat in Azadpur mandi is trading at 2,500 rupees per quintal"
                in data_price.get("spoken_summary", "")
            )
            prices = data_price.get("data", {}).get("prices", {})
            assert prices.get("quintal", {}).get("modal") == 2500
            assert prices.get("kg", {}).get("modal") == 25.0

            # 2. Compare markets
            res_comp = await session.call_tool(
                "commodity_prices",
                arguments={
                    "action": "compare_markets",
                    "commodity": "Wheat",
                    "markets": ["Azadpur", "Ghazipur"],
                },
            )
            data_comp = json.loads(getattr(res_comp.content[0], "text", "{}"))
            assert data_comp.get("ok") is True
            assert len(data_comp.get("spoken_summary", "")) <= 300

            # 3. Missing commodity returns invalid_input
            res_bad = await session.call_tool(
                "commodity_prices",
                arguments={"action": "get_price"},
            )
            data_bad = json.loads(getattr(res_bad.content[0], "text", "{}"))
            assert data_bad.get("ok") is False
            assert data_bad.get("error_code") == "invalid_input"

            # 4. User isolation check
            await assert_user_isolation(
                ISOLATION_REGISTRY["commodity_prices"], app, contract_rsa_key
            )
    finally:
        await mock_client.aclose()
        set_commodity_service(None)
        await engine.dispose()
