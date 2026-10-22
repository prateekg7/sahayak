"""Namespaced JSON cache access and Redis-backed distributed locks."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TypeVar
from uuid import uuid4

from redis.asyncio import Redis

T = TypeVar("T")


class Cache:
    """Constrain Redis access to namespaced, JSON-serializable values."""

    def __init__(self, client: Redis, namespace: str = "sahayak") -> None:
        self._client = client
        self._namespace = namespace

    def _key(self, key: str) -> str:
        return f"{self._namespace}:{key}"

    async def get_json(self, key: str) -> object | None:
        """Read and decode a JSON value, returning ``None`` on a cache miss."""
        value = await self._client.get(self._key(key))
        return None if value is None else json.loads(value)

    async def set_json(self, key: str, value: object, ttl_seconds: int) -> None:
        """Store JSON with a required positive expiration time."""
        await self._client.set(self._key(key), json.dumps(value), ex=ttl_seconds)

    @asynccontextmanager
    async def lock(self, key: str, ttl_seconds: int) -> AsyncIterator[bool]:
        """Attempt an expiring distributed lock and release only the caller's token."""
        lock_key = self._key(f"lock:{key}")
        token = str(uuid4())
        acquired = bool(await self._client.set(lock_key, token, nx=True, ex=ttl_seconds))
        try:
            yield acquired
        finally:
            if acquired and await self._client.get(lock_key) == token:
                await self._client.delete(lock_key)
