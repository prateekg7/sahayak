"""Unit tests for commodity service and adapter integration (T12.3)."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from sahayak.modules.local_info.adapters.commodity import CommodityHttpDataSource
from sahayak.modules.local_info.service.commodity import CommodityService


@pytest.mark.asyncio
async def test_commodity_service_get_price_happy_path() -> None:
    now = datetime(2026, 10, 24, 12, 0, 0, tzinfo=UTC)

    def fake_handler(request: httpx.Request) -> httpx.Response:
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
        return httpx.Response(404)

    transport = httpx.MockTransport(fake_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = CommodityHttpDataSource(http_client=client, clock=lambda: now)
        service = CommodityService(data_source=adapter)

        # Inquire with Hindi crop name "gehun"
        spoken, data = await service.get_price("gehun", "Azadpur")
        assert len(spoken) <= 300
        assert "Wheat in Azadpur mandi is trading at 2,500 rupees per quintal" in spoken
        assert "about 25 rupees per kilogram" in spoken
        assert data["commodity"] == "Wheat"
        assert data["prices"]["quintal"]["modal"] == 2500
        assert data["prices"]["kg"]["modal"] == 25.0
        assert data["source"]["source_id"] == "agmarknet"


@pytest.mark.asyncio
async def test_commodity_service_compare_markets() -> None:
    now = datetime(2026, 10, 24, 12, 0, 0, tzinfo=UTC)

    def fake_handler(request: httpx.Request) -> httpx.Response:
        market = request.url.params.get("market", "")
        modal = 3200 if "azadpur" in market else 3000
        return httpx.Response(
            200,
            json={
                "record": {
                    "commodity": "Onion",
                    "market": market.title(),
                    "state": "NCT of Delhi",
                    "arrival_date": "2026-10-24",
                    "min_price": modal - 200,
                    "max_price": modal + 200,
                    "modal_price": modal,
                }
            },
        )

    transport = httpx.MockTransport(fake_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = CommodityHttpDataSource(http_client=client, clock=lambda: now)
        service = CommodityService(data_source=adapter)

        spoken, data = await service.compare_markets("pyaz", ["Azadpur", "Ghazipur"])
        assert len(spoken) <= 300
        assert "Onion prices:" in spoken
        assert len(data["markets"]) == 2
        assert data["markets"][0]["modal_price_kg"] == 32.0
        assert data["markets"][1]["modal_price_kg"] == 30.0


@pytest.mark.asyncio
async def test_commodity_service_trend() -> None:
    now = datetime(2026, 10, 24, 12, 0, 0, tzinfo=UTC)

    def fake_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "trend": {
                    "current_modal_kg": 28.0,
                    "previous_modal_kg": 24.0,
                    "change_pct": 16.7,
                    "direction": "up",
                }
            },
        )

    transport = httpx.MockTransport(fake_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = CommodityHttpDataSource(http_client=client, clock=lambda: now)
        service = CommodityService(data_source=adapter)

        spoken, data = await service.get_trend("tamatar", "Azadpur")
        assert len(spoken) <= 300
        assert "Tomato prices in Azadpur rose by 17 percent" in spoken
        assert data["direction"] == "up"
        assert data["current_modal_kg"] == 28.0


@pytest.mark.asyncio
async def test_commodity_service_upstream_fallback() -> None:
    now = datetime(2026, 10, 24, 12, 0, 0, tzinfo=UTC)

    def fake_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    transport = httpx.MockTransport(fake_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = CommodityHttpDataSource(http_client=client, clock=lambda: now, max_retries=1)
        service = CommodityService(data_source=adapter)

        spoken, data = await service.get_price("Wheat", "Azadpur")
        assert len(spoken) <= 300
        # Falls back to benchmark rate
        assert data["prices"]["quintal"]["modal"] == 2450
        assert data["source"]["is_stale"] is True
