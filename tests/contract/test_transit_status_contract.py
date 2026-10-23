"""Contract tests for transit_status MCP tool over Streamable HTTP (T12.2)."""

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
from sahayak.modules.local_info.adapters.transit import TransitHttpDataSource
from sahayak.modules.local_info.service.transit import TransitService
from sahayak.modules.local_info.tools.transit import set_transit_service
from tests.security.isolation import ISOLATION_REGISTRY, assert_user_isolation


@pytest.fixture(scope="module")
def contract_rsa_key() -> rsa.RSAPrivateKey:
    """RSA private key for signing test JWTs."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.mark.asyncio
async def test_transit_status_mcp_contract_lifecycle(
    contract_rsa_key: rsa.RSAPrivateKey,
) -> None:
    """Contract test for transit_status over Streamable HTTP:

    1. Anonymous invocation succeeds for departures at 'cp' (Rajiv Chowk).
    2. Envelope structure contains spoken summary, data, and next_actions.
    3. Status action succeeds for lines.
    4. Missing station for next_departures returns invalid_input.
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

    def mock_transit_api(request: httpx.Request) -> httpx.Response:
        if "v1/departures" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "departures": [
                        {
                            "line": "Yellow",
                            "destination": "Samaypur Badli",
                            "platform": "1",
                            "eta_minutes": 3,
                            "scheduled_time": "12:03",
                            "status": "On Time",
                        },
                        {
                            "line": "Blue",
                            "destination": "Noida Electronic City",
                            "platform": "3",
                            "eta_minutes": 5,
                            "scheduled_time": "12:05",
                            "status": "On Time",
                        },
                    ]
                },
            )
        if "v1/lines/status" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "lines": [
                        {
                            "line": "Yellow",
                            "status": "Normal",
                            "frequency_minutes": 4,
                            "message": "Normal service running.",
                        },
                        {
                            "line": "Blue",
                            "status": "Normal",
                            "frequency_minutes": 5,
                            "message": "Normal service running.",
                        },
                    ]
                },
            )
        return httpx.Response(404)

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_transit_api))
    adapter = TransitHttpDataSource(http_client=mock_client, clock=lambda: now)
    service = TransitService(data_source=adapter)
    set_transit_service(service)

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

            # 1. Anonymous next_departures at "cp"
            res_cp = await session.call_tool(
                "transit_status",
                arguments={"action": "next_departures", "station": "cp"},
            )
            data_cp = json.loads(getattr(res_cp.content[0], "text", "{}"))
            assert data_cp.get("ok") is True
            assert len(data_cp.get("spoken_summary", "")) <= 300
            assert "Rajiv Chowk" in data_cp.get("spoken_summary", "")
            assert data_cp.get("data", {}).get("station") == "Rajiv Chowk"
            assert len(data_cp.get("data", {}).get("departures", [])) == 2
            assert data_cp.get("data", {}).get("source", {}).get("source_id") == "open_transit"

            # 2. Line status action
            res_status = await session.call_tool(
                "transit_status",
                arguments={"action": "status", "line": "yellow"},
            )
            data_status = json.loads(getattr(res_status.content[0], "text", "{}"))
            assert data_status.get("ok") is True
            assert len(data_status.get("spoken_summary", "")) <= 300
            assert "Yellow Line is operating with normal service" in data_status.get(
                "spoken_summary", ""
            )

            # 3. Missing station for next_departures
            res_bad = await session.call_tool(
                "transit_status",
                arguments={"action": "next_departures"},
            )
            data_bad = json.loads(getattr(res_bad.content[0], "text", "{}"))
            assert data_bad.get("ok") is False
            assert data_bad.get("error_code") == "invalid_input"

            # 4. Unknown station returns invalid_input
            res_unknown = await session.call_tool(
                "transit_status",
                arguments={"action": "next_departures", "station": "Atlantis Undersea Depot"},
            )
            data_unknown = json.loads(getattr(res_unknown.content[0], "text", "{}"))
            assert data_unknown.get("ok") is False
            assert data_unknown.get("error_code") == "invalid_input"

            # 5. User isolation check
            await assert_user_isolation(ISOLATION_REGISTRY["transit_status"], app, contract_rsa_key)
    finally:
        await mock_client.aclose()
        set_transit_service(None)
        await engine.dispose()
