"""Tests for cache namespacing, TTLs, and locks."""

from __future__ import annotations

import fakeredis.aioredis
import pytest

from sahayak.core.cache import Cache


@pytest.mark.asyncio
async def test_json_values_are_namespaced_and_expire() -> None:
    """Cache values are isolated by prefix and use the requested expiration."""
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    cache = Cache(redis, namespace="test")
    await cache.set_json("answer", {"value": 42}, ttl_seconds=1)

    assert await cache.get_json("answer") == {"value": 42}
    assert await redis.ttl("test:answer") > 0


@pytest.mark.asyncio
async def test_lock_allows_only_one_holder() -> None:
    """A lock is released after its owner exits and blocks concurrent holders."""
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    cache = Cache(redis)

    async with cache.lock("topic", ttl_seconds=10) as acquired:
        assert acquired is True
        async with cache.lock("topic", ttl_seconds=10) as duplicate:
            assert duplicate is False

    async with cache.lock("topic", ttl_seconds=10) as acquired_again:
        assert acquired_again is True
