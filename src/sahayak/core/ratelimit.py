"""Atomic Redis sliding-window request limits."""

from __future__ import annotations

import time
from dataclasses import dataclass
from uuid import uuid4

from redis.asyncio import Redis
from redis.exceptions import WatchError


@dataclass(frozen=True)
class RateLimit:
    """A named sliding-window limit expressed in requests per period."""

    name: str
    limit: int
    window_seconds: int = 60


class RateLimiter:
    """Apply named, atomic limits keyed by already hashed client identity."""

    def __init__(self, client: Redis, namespace: str = "sahayak") -> None:
        self._client = client
        self._namespace = namespace

    async def allow(self, rate_limit: RateLimit, identity_hash: str) -> bool:
        """Return whether the current request may proceed under the named limit."""
        now_ms = int(time.time() * 1000)
        key = f"{self._namespace}:ratelimit:{rate_limit.name}:{identity_hash}"
        window_ms = rate_limit.window_seconds * 1000
        while True:
            async with self._client.pipeline(transaction=True) as pipeline:
                try:
                    await pipeline.watch(key)
                    await pipeline.zremrangebyscore(key, "-inf", now_ms - window_ms)
                    if await pipeline.zcard(key) >= rate_limit.limit:
                        await pipeline.unwatch()  # type: ignore[no-untyped-call]
                        return False
                    pipeline.multi()  # type: ignore[no-untyped-call]
                    pipeline.zadd(key, {f"{now_ms}:{uuid4()}": now_ms})
                    pipeline.pexpire(key, window_ms)
                    await pipeline.execute()
                    return True
                except WatchError:
                    continue
