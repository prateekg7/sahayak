"""Rate limiting security regression tests (T1.9)."""

from __future__ import annotations

from typing import Any

import pytest

from sahayak.core.ratelimit import RateLimit, RateLimiter


@pytest.fixture
def fake_redis() -> Any:
    """Create a fakeredis client instance."""
    import fakeredis.aioredis

    return fakeredis.aioredis.FakeRedis()


@pytest.mark.asyncio
async def test_rate_limiter_burst_and_principal_isolation(fake_redis: Any) -> None:
    """Burst beyond limit blocks principal, while other principals remain unimpacted."""
    limiter = RateLimiter(client=fake_redis)
    limit = RateLimit(name="test_tool", limit=5, window_seconds=10)

    # User A performs 5 calls within limit
    for _ in range(limit.limit):
        allowed = await limiter.allow(
            rate_limit=limit,
            identity_hash="user-a",
        )
        assert allowed is True

    # User A's 6th call is blocked
    blocked_a = await limiter.allow(
        rate_limit=limit,
        identity_hash="user-a",
    )
    assert blocked_a is False

    # User B is NOT impacted by User A's rate limit exhaustion
    allowed_b = await limiter.allow(
        rate_limit=limit,
        identity_hash="user-b",
    )
    assert allowed_b is True


@pytest.mark.asyncio
async def test_ip_based_rate_limiting_isolation(fake_redis: Any) -> None:
    """IP hash rate limit isolates different client IP addresses."""
    limiter = RateLimiter(client=fake_redis)
    limit = RateLimit(name="ip_limit", limit=3, window_seconds=5)

    ip1 = "ip_hash_192_168_1_1"
    ip2 = "ip_hash_10_0_0_1"

    for _ in range(limit.limit):
        assert await limiter.allow(rate_limit=limit, identity_hash=ip1)

    # ip1 is now rate-limited
    assert not await limiter.allow(rate_limit=limit, identity_hash=ip1)

    # ip2 is clean
    assert await limiter.allow(rate_limit=limit, identity_hash=ip2)
