"""Tests for the Redis-backed sliding-window limiter."""

from __future__ import annotations

import asyncio

import fakeredis.aioredis
import pytest

from sahayak.core.ratelimit import RateLimit, RateLimiter


@pytest.mark.asyncio
async def test_limiter_blocks_the_n_plus_one_request() -> None:
    """The N+1 request is rejected from a shared Redis window."""
    limiter = RateLimiter(fakeredis.aioredis.FakeRedis(decode_responses=True))
    limit = RateLimit(name="tools", limit=2)

    assert await limiter.allow(limit, "principal-hash") is True
    assert await limiter.allow(limit, "principal-hash") is True
    assert await limiter.allow(limit, "principal-hash") is False


@pytest.mark.asyncio
async def test_limiter_is_atomic_under_concurrent_requests() -> None:
    """Concurrent callers cannot exceed the shared request budget."""
    limiter = RateLimiter(fakeredis.aioredis.FakeRedis(decode_responses=True))
    limit = RateLimit(name="generation", limit=3)

    results = await asyncio.gather(*(limiter.allow(limit, "principal-hash") for _ in range(10)))

    assert sum(results) == 3
