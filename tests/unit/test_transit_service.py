"""Unit tests for transit service and adapter integration (T12.2)."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from sahayak.modules.local_info.adapters.transit import TransitHttpDataSource
from sahayak.modules.local_info.service.transit import TransitService


@pytest.mark.asyncio
async def test_transit_service_departures_happy_path() -> None:
    now = datetime(2026, 10, 24, 12, 0, 0, tzinfo=UTC)

    def fake_handler(request: httpx.Request) -> httpx.Response:
        if "v1/departures" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "departures": [
                        {
                            "line": "Yellow",
                            "destination": "Samaypur Badli",
                            "platform": "1",
                            "eta_minutes": 2,
                            "scheduled_time": "12:02",
                            "status": "On Time",
                        },
                        {
                            "line": "Blue",
                            "destination": "Dwarka Sector 21",
                            "platform": "4",
                            "eta_minutes": 4,
                            "scheduled_time": "12:04",
                            "status": "On Time",
                        },
                    ]
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(fake_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = TransitHttpDataSource(
            http_client=client,
            clock=lambda: now,
        )
        service = TransitService(data_source=adapter)

        # Departures query for "cp"
        spoken, data = await service.get_next_departures("cp")
        assert len(spoken) <= 300
        assert "Rajiv Chowk" in spoken
        assert "Yellow Line toward Samaypur Badli in 2 minutes on platform 1" in spoken
        assert data["station"] == "Rajiv Chowk"
        assert len(data["departures"]) == 2
        assert data["source"]["source_id"] == "open_transit"
        assert data["source"]["is_stale"] is False


@pytest.mark.asyncio
async def test_transit_service_departures_filtering() -> None:
    now = datetime(2026, 10, 24, 12, 0, 0, tzinfo=UTC)

    def fake_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "departures": [
                    {
                        "line": "Yellow",
                        "destination": "Samaypur Badli",
                        "platform": "1",
                        "eta_minutes": 2,
                    },
                    {
                        "line": "Blue",
                        "destination": "Noida City Centre",
                        "platform": "3",
                        "eta_minutes": 5,
                    },
                ]
            },
        )

    transport = httpx.MockTransport(fake_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = TransitHttpDataSource(
            http_client=client,
            clock=lambda: now,
        )
        service = TransitService(data_source=adapter)

        spoken, data = await service.get_next_departures("Rajiv Chowk", line_filter="blue")
        assert len(data["departures"]) == 1
        assert data["departures"][0]["line"] == "Blue"


@pytest.mark.asyncio
async def test_transit_service_upstream_failure_uses_fallback() -> None:
    now = datetime(2026, 10, 24, 12, 0, 0, tzinfo=UTC)

    def fake_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    transport = httpx.MockTransport(fake_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = TransitHttpDataSource(
            http_client=client,
            clock=lambda: now,
            max_retries=1,
        )
        service = TransitService(data_source=adapter)

        spoken, data = await service.get_next_departures("Hauz Khas")
        assert len(spoken) <= 300
        assert "Hauz Khas" in spoken
        # Falls back to standard headway departures
        assert len(data["departures"]) >= 1
        assert data["source"]["is_stale"] is True


@pytest.mark.asyncio
async def test_transit_service_line_status() -> None:
    now = datetime(2026, 10, 24, 12, 0, 0, tzinfo=UTC)

    def fake_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "lines": [
                    {
                        "line": "Yellow",
                        "status": "Normal",
                        "frequency_minutes": 4,
                        "message": "Service normal.",
                    },
                    {
                        "line": "Airport Express",
                        "status": "Normal",
                        "frequency_minutes": 10,
                        "message": "Express running on schedule.",
                    },
                ]
            },
        )

    transport = httpx.MockTransport(fake_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = TransitHttpDataSource(
            http_client=client,
            clock=lambda: now,
        )
        service = TransitService(data_source=adapter)

        spoken, data = await service.get_line_status(line_filter="yellow")
        assert len(spoken) <= 300
        assert "Yellow Line is operating with normal service" in spoken
        assert len(data["lines"]) == 1
        assert data["lines"][0]["line"] == "Yellow"
