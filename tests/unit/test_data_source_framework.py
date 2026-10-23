"""Unit tests for external data-source adapter framework and resilience policies (T12.1)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from sahayak.core.errors import InvalidInputError, UpstreamUnavailableError
from sahayak.core.module import ModuleRegistry
from sahayak.modules.local_info.adapters.base import BaseHttpDataSource
from sahayak.modules.local_info.adapters.circuit_breaker import (
    CircuitState,
    DataSourceCircuitBreaker,
)
from sahayak.modules.local_info.domain.attribution import (
    clean_spoken_text,
    format_data_answer_spoken,
    format_freshness_spoken,
    format_relative_time_spoken,
    format_spoken_attribution,
)
from sahayak.modules.local_info.ports import DataSourceResult


def test_clean_spoken_text_strips_markdown_and_symbols() -> None:
    raw = "**Alert**: *Train* `12002` [Departing] {Platform #3} <On Time> ~5m~ 'Express'!"
    clean = clean_spoken_text(raw)
    assert "*" not in clean
    assert "`" not in clean
    assert "[" not in clean
    assert "{" not in clean
    assert "<" not in clean
    assert "'" not in clean
    assert "Alert: Train 12002 Departing Platform 3 On Time 5m Express!" in clean


def test_relative_time_formatting() -> None:
    now = datetime(2026, 10, 24, 12, 0, 0, tzinfo=UTC)

    t_just_now = now - timedelta(seconds=45)
    assert format_relative_time_spoken(t_just_now, now) == "just now"

    t_15m = now - timedelta(minutes=15)
    assert format_relative_time_spoken(t_15m, now) == "about 15 minutes ago"

    t_2h = now - timedelta(hours=2)
    assert format_relative_time_spoken(t_2h, now) == "about 2 hours ago"

    t_1d = now - timedelta(days=1)
    assert format_relative_time_spoken(t_1d, now) == "about 1 day ago"


def test_attribution_and_freshness_spoken_formatting() -> None:
    now = datetime(2026, 10, 24, 12, 0, 0, tzinfo=UTC)
    assert (
        format_spoken_attribution("Delhi Metro Rail", "Data by DMRC")
        == "According to Delhi Metro Rail"
    )

    fresh_res: DataSourceResult[dict[str, str]] = DataSourceResult(
        data={"status": "normal"},
        source_id="test_transit",
        source_name="Delhi Metro Rail",
        license="Open Data License",
        attribution="Data provided by DMRC",
        fetched_at=now - timedelta(minutes=3),
        is_stale=False,
    )
    freshness_spoken = format_freshness_spoken(fresh_res, now)
    assert "As of about 3 minutes ago" in freshness_spoken

    stale_res: DataSourceResult[dict[str, str]] = DataSourceResult(
        data={"status": "normal"},
        source_id="test_transit",
        source_name="Delhi Metro Rail",
        license="Open Data License",
        attribution="Data provided by DMRC",
        fetched_at=now,
        is_stale=True,
        cached_at=now - timedelta(hours=1),
    )
    stale_spoken = format_freshness_spoken(stale_res, now)
    assert "Using cached update from about 1 hour ago" in stale_spoken

    spoken_summary = format_data_answer_spoken(
        prefix="Yellow Line is operating on time",
        body="Next train arrives at Rajiv Chowk in 4 minutes",
        freshness=freshness_spoken,
        source_name=fresh_res.source_name,
    )
    assert "According to Delhi Metro Rail" in spoken_summary
    assert "As of about 3 minutes ago" in spoken_summary
    assert len(spoken_summary) <= 300


@pytest.mark.asyncio
async def test_allow_listed_host_validation() -> None:
    # Creating with disallowed base_url host fails immediately
    with pytest.raises(InvalidInputError, match="not permitted"):
        BaseHttpDataSource[dict[str, Any]](
            source_id="malicious_source",
            source_name="Malicious Source",
            base_url="https://evil.internal.network/api",
            license="None",
            attribution="None",
            allow_listed_hosts=["api.data.gov.in"],
        )


@pytest.mark.asyncio
async def test_fresh_caching_and_mock_http_execution() -> None:
    now = datetime(2026, 10, 24, 10, 0, 0, tzinfo=UTC)
    request_count = 0

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(200, json={"station": "NDLS", "status": "ON_TIME"})

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = BaseHttpDataSource[dict[str, Any]](
            source_id="mock_transit",
            source_name="Mock Transit API",
            base_url="https://transit.example.com/api",
            license="ODbL 1.0",
            attribution="Transit open data",
            allow_listed_hosts=["transit.example.com"],
            default_ttl_seconds=300,
            http_client=client,
            clock=lambda: now,
        )

        # 1. First fetch: reaches upstream
        res1 = await adapter.fetch_json("departures", params={"station": "NDLS"})
        assert request_count == 1
        assert res1.is_stale is False
        assert res1.data["status"] == "ON_TIME"

        # 2. Second fetch within TTL: served from fresh cache, no HTTP call
        res2 = await adapter.fetch_json("departures", params={"station": "NDLS"})
        assert request_count == 1, "Cache hit must not execute upstream HTTP call"
        assert res2.is_stale is False
        assert res2.data["station"] == "NDLS"


@pytest.mark.asyncio
async def test_bounded_retries_and_recovery() -> None:
    attempts = 0

    def transient_failure_handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(500, json={"error": "temporary upstream glitch"})
        return httpx.Response(200, json={"commodity": "wheat", "modal_price": 2400})

    transport = httpx.MockTransport(transient_failure_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = BaseHttpDataSource[dict[str, Any]](
            source_id="mock_agmark",
            source_name="Mock Agmarknet",
            base_url="https://agmark.example.com",
            license="Open Gov Data",
            attribution="Ministry of Agriculture",
            allow_listed_hosts=["agmark.example.com"],
            default_ttl_seconds=120,
            max_retries=2,
            http_client=client,
        )

        res = await adapter.fetch_json("prices", params={"crop": "wheat"})
        assert attempts == 3, "Should succeed on 3rd attempt (after 2 retries)"
        assert res.is_stale is False
        assert res.data["commodity"] == "wheat"
        assert adapter.circuit_breaker.consecutive_failures == 0


@pytest.mark.asyncio
async def test_stale_while_error_fallback_on_outage() -> None:
    now = datetime(2026, 10, 24, 8, 0, 0, tzinfo=UTC)
    upstream_online = True

    def toggle_handler(request: httpx.Request) -> httpx.Response:
        if not upstream_online:
            return httpx.Response(503, json={"error": "service unavailable"})
        return httpx.Response(200, json={"route": "Line 1", "headway_minutes": 5})

    transport = httpx.MockTransport(toggle_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = BaseHttpDataSource[dict[str, Any]](
            source_id="mock_bus",
            source_name="City Bus Transit",
            base_url="https://bus.example.com",
            license="City Open Data",
            attribution="City Transport Corp",
            allow_listed_hosts=["bus.example.com"],
            default_ttl_seconds=60,
            stale_ttl_seconds=3600,
            max_retries=1,
            http_client=client,
            clock=lambda: now,
        )

        # 1. Successful fetch populates fresh and stale cache
        res_fresh = await adapter.fetch_json("headway")
        assert res_fresh.is_stale is False
        assert res_fresh.data["headway_minutes"] == 5

        # 2. Advance time past fresh TTL (60s), and upstream goes offline
        now = now + timedelta(seconds=120)
        upstream_online = False

        # 3. Request triggers retries, upstream fails, returns cached stale data
        res_stale = await adapter.fetch_json("headway")
        assert res_stale.is_stale is True
        assert res_stale.data["headway_minutes"] == 5
        assert res_stale.cached_at is not None

        # 4. If request has no stale cached data, it raises UpstreamUnavailableError
        with pytest.raises(UpstreamUnavailableError, match="could not reach"):
            await adapter.fetch_json("unknown_route")


@pytest.mark.asyncio
async def test_circuit_breaker_trips_and_serves_stale_cache() -> None:
    now = datetime(2026, 10, 24, 15, 0, 0, tzinfo=UTC)
    upstream_calls = 0

    def failing_handler(request: httpx.Request) -> httpx.Response:
        nonlocal upstream_calls
        upstream_calls += 1
        return httpx.Response(502, text="Bad Gateway")

    transport = httpx.MockTransport(failing_handler)
    cb = DataSourceCircuitBreaker(
        source_id="failing_source",
        failure_threshold=2,
        recovery_timeout_seconds=60.0,
    )

    async with httpx.AsyncClient(transport=transport) as client:
        adapter = BaseHttpDataSource[dict[str, Any]](
            source_id="failing_source",
            source_name="Failing Source",
            base_url="https://api.external.com",
            license="Open",
            attribution="External API",
            allow_listed_hosts=["api.external.com"],
            default_ttl_seconds=30,
            max_retries=0,
            circuit_breaker=cb,
            http_client=client,
            clock=lambda: now,
        )

        # Preload cache and advance clock past fresh TTL (30s)
        await adapter._set_cache("failing_source:live:", {"status": "degraded_cached"})
        now = now + timedelta(seconds=45)

        # Failure 1
        res1 = await adapter.fetch_json("live")
        assert res1.is_stale is True
        assert cb.consecutive_failures == 1
        assert cb.state == CircuitState.CLOSED

        # Failure 2 trips circuit breaker to OPEN
        res2 = await adapter.fetch_json("live")
        assert res2.is_stale is True
        assert cb.is_open is True

        # When circuit is OPEN, further calls return stale cache immediately without HTTP call
        prev_calls = upstream_calls
        res3 = await adapter.fetch_json("live")
        assert res3.is_stale is True
        assert upstream_calls == prev_calls, "Open circuit must not make outbound HTTP calls"


def test_module_registry_discovery() -> None:
    registry = ModuleRegistry()
    registry.load(["local_info"])
    assert "local_info" in registry.modules
    mod = registry.modules["local_info"]
    assert mod.name == "local_info"
    assert mod.version == "0.1.0"
    assert mod.health().healthy is True
