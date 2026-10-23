"""Resilient HTTP data-source adapter base with caching and circuit breaking (T12.1)."""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.parse
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Generic, TypeVar

import httpx

from sahayak.core.cache import Cache
from sahayak.core.errors import InvalidInputError, UpstreamUnavailableError
from sahayak.modules.local_info.adapters.circuit_breaker import DataSourceCircuitBreaker
from sahayak.modules.local_info.ports import DataSourcePort, DataSourceResult

logger = logging.getLogger(__name__)

T = TypeVar("T")


class BaseHttpDataSource(DataSourcePort[T], Generic[T]):
    """Base adapter for external HTTP data sources.

    Features:
    - Host allow-listing to prevent SSRF.
    - Three-state circuit breaker per data source.
    - Bounded retries with exponential backoff on transient errors.
    - Two-tier caching: fresh cache (normal TTL) and stale cache (24h TTL).
    - Stale-while-error policy: returns cached stale data on upstream outages.
    """

    def __init__(
        self,
        *,
        source_id: str,
        source_name: str,
        base_url: str,
        license: str,
        attribution: str,
        allow_listed_hosts: list[str],
        default_ttl_seconds: int = 300,
        stale_ttl_seconds: int = 86400,
        http_client: httpx.AsyncClient | None = None,
        cache: Cache | None = None,
        circuit_breaker: DataSourceCircuitBreaker | None = None,
        timeout_seconds: float = 2.0,
        max_retries: int = 2,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._source_id = source_id
        self._source_name = source_name
        self._base_url = base_url.rstrip("/")
        self._license = license
        self._attribution = attribution
        self._allow_listed_hosts = set(h.lower() for h in allow_listed_hosts)
        self._default_ttl_seconds = max(10, default_ttl_seconds)
        self._stale_ttl_seconds = max(self._default_ttl_seconds, stale_ttl_seconds)
        self._client = http_client
        self._cache = cache
        self._circuit_breaker = circuit_breaker or DataSourceCircuitBreaker(source_id)
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._clock = clock or (lambda: datetime.now(UTC))

        # In-memory cache fallback when Redis is absent
        self._mem_fresh_cache: dict[str, tuple[datetime, Any]] = {}
        self._mem_stale_cache: dict[str, tuple[datetime, Any]] = {}

        # Validate base url host
        self._validate_url(self._base_url)

    @property
    def source_id(self) -> str:
        return self._source_id

    @property
    def source_name(self) -> str:
        return self._source_name

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def license(self) -> str:
        return self._license

    @property
    def attribution(self) -> str:
        return self._attribution

    @property
    def default_ttl_seconds(self) -> int:
        return self._default_ttl_seconds

    @property
    def circuit_breaker(self) -> DataSourceCircuitBreaker:
        return self._circuit_breaker

    def _validate_url(self, url: str) -> None:
        """Verify that target URL belongs to an allow-listed host."""
        parsed = urllib.parse.urlparse(url)
        host = (parsed.hostname or "").lower()
        if host not in self._allow_listed_hosts:
            raise InvalidInputError(
                spoken=f"Outbound access to {host or 'external host'} is not permitted.",
                detail=f"Host '{host}' is not in allow-listed hosts: {self._allow_listed_hosts}",
            )

    def _build_cache_key(self, endpoint: str, params: dict[str, Any] | None) -> str:
        param_str = ""
        if params:
            param_str = urllib.parse.urlencode(sorted(params.items()))
        clean_ep = endpoint.strip("/").replace("/", "_")
        return f"{self._source_id}:{clean_ep}:{param_str}"

    async def _get_fresh(self, key: str) -> tuple[datetime, Any] | None:
        if self._cache:
            val = await self._cache.get_json(f"ds_fresh:{key}")
            if isinstance(val, dict) and "cached_at" in val and "data" in val:
                return datetime.fromisoformat(val["cached_at"]), val["data"]
            return None
        now = self._clock()
        entry = self._mem_fresh_cache.get(key)
        if entry:
            cached_at, data = entry
            if (now - cached_at).total_seconds() <= self._default_ttl_seconds:
                return cached_at, data
            del self._mem_fresh_cache[key]
        return None

    async def _get_stale(self, key: str) -> tuple[datetime, Any] | None:
        if self._cache:
            val = await self._cache.get_json(f"ds_stale:{key}")
            if isinstance(val, dict) and "cached_at" in val and "data" in val:
                return datetime.fromisoformat(val["cached_at"]), val["data"]
            return None
        now = self._clock()
        entry = self._mem_stale_cache.get(key)
        if entry:
            cached_at, data = entry
            if (now - cached_at).total_seconds() <= self._stale_ttl_seconds:
                return cached_at, data
            del self._mem_stale_cache[key]
        return None

    async def _set_cache(self, key: str, data: Any) -> None:
        now = self._clock()
        payload = {"cached_at": now.isoformat(), "data": data}
        if self._cache:
            await self._cache.set_json(
                f"ds_fresh:{key}",
                payload,
                ttl_seconds=self._default_ttl_seconds,
            )
            await self._cache.set_json(
                f"ds_stale:{key}",
                payload,
                ttl_seconds=self._stale_ttl_seconds,
            )
        else:
            self._mem_fresh_cache[key] = (now, data)
            self._mem_stale_cache[key] = (now, data)

    async def fetch_json(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        parser: Callable[[Any], T] | None = None,
    ) -> DataSourceResult[T]:
        """Fetch JSON data with caching, circuit breaker, retries, and stale fallback."""
        full_url = f"{self._base_url}/{endpoint.lstrip('/')}"
        self._validate_url(full_url)
        now = self._clock()
        cache_key = self._build_cache_key(endpoint, params)

        # 1. Check fresh cache
        fresh_hit = await self._get_fresh(cache_key)
        if fresh_hit is not None:
            cached_at, raw_data = fresh_hit
            parsed_data = parser(raw_data) if parser else raw_data
            return DataSourceResult(
                data=parsed_data,
                source_id=self._source_id,
                source_name=self._source_name,
                license=self._license,
                attribution=self._attribution,
                fetched_at=now,
                is_stale=False,
                cached_at=cached_at,
            )

        # 2. Check circuit breaker
        if self._circuit_breaker.is_open:
            stale_hit = await self._get_stale(cache_key)
            if stale_hit is not None:
                cached_at, raw_data = stale_hit
                parsed_data = parser(raw_data) if parser else raw_data
                return DataSourceResult(
                    data=parsed_data,
                    source_id=self._source_id,
                    source_name=self._source_name,
                    license=self._license,
                    attribution=self._attribution,
                    fetched_at=now,
                    is_stale=True,
                    cached_at=cached_at,
                )
            raise UpstreamUnavailableError(
                spoken=f"{self._source_name} is currently unavailable. Please try again soon.",
                detail=f"Circuit breaker is OPEN for {self._source_id}",
            )

        # 3. Outbound HTTP with retries
        last_exception: Exception | None = None
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient()

        try:
            for attempt in range(self._max_retries + 1):
                try:
                    res = await client.get(
                        full_url,
                        params=params,
                        timeout=self._timeout_seconds,
                    )
                    res.raise_for_status()
                    raw_data = res.json()
                    parsed_data = parser(raw_data) if parser else raw_data

                    # Success: record in circuit breaker and store in cache
                    self._circuit_breaker.record_success()
                    # Store serialized data in cache
                    serializable = (
                        raw_data
                        if isinstance(raw_data, dict | list | str | int | float | bool)
                        else json.loads(json.dumps(raw_data))
                    )
                    await self._set_cache(cache_key, serializable)

                    return DataSourceResult(
                        data=parsed_data,
                        source_id=self._source_id,
                        source_name=self._source_name,
                        license=self._license,
                        attribution=self._attribution,
                        fetched_at=now,
                        is_stale=False,
                        cached_at=now,
                    )
                except (httpx.HTTPError, httpx.TimeoutException, OSError) as exc:
                    last_exception = exc
                    if attempt < self._max_retries:
                        backoff = min(0.5, 0.05 * (2**attempt))
                        await asyncio.sleep(backoff)
                        continue
                    break

            # If all retries failed:
            self._circuit_breaker.record_failure()
            logger.warning(
                "Outbound call to %s failed after %d retries: %s",
                full_url,
                self._max_retries,
                last_exception,
            )

            # Stale-while-error fallback
            stale_hit = await self._get_stale(cache_key)
            if stale_hit is not None:
                cached_at, raw_data = stale_hit
                parsed_data = parser(raw_data) if parser else raw_data
                return DataSourceResult(
                    data=parsed_data,
                    source_id=self._source_id,
                    source_name=self._source_name,
                    license=self._license,
                    attribution=self._attribution,
                    fetched_at=now,
                    is_stale=True,
                    cached_at=cached_at,
                )

            raise UpstreamUnavailableError(
                spoken=f"I could not reach {self._source_name} right now. Please try again soon.",
                detail=f"Outbound request to {full_url} failed: {last_exception}",
            )
        finally:
            if owns_client:
                await client.aclose()
