"""Daily request and token budget enforcement for LLM invocations."""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from sahayak.shared.llm.ports import BudgetExceededError

if TYPE_CHECKING:
    from redis.asyncio import Redis


class DailyBudgetManager:
    """Track and enforce daily request and token ceilings across all LLM providers."""

    def __init__(
        self,
        *,
        redis: Redis | None = None,
        daily_request_limit: int = 1000,
    ) -> None:
        self._redis = redis
        self.daily_request_limit = daily_request_limit
        # In-memory counters used as fallback when Redis is not provided
        self._memory_requests: dict[str, int] = {}
        self._memory_tokens: dict[str, int] = {}

    def _today_key(self, metric: str) -> str:
        today = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d")
        return f"llm:budget:{metric}:{today}"

    async def check_and_increment_request(self) -> int:
        """Atomically check and increment the daily request count.

        Returns:
            The new request count for the day.

        Raises:
            BudgetExceededError: If the daily request ceiling has been reached.
        """
        key = self._today_key("requests")

        if self._redis is not None:
            count = await self._redis.incr(key)
            if count == 1:
                # Expire after 48 hours to clean up automatically
                await self._redis.expire(key, 172800)
            if count > self.daily_request_limit:
                detail = (
                    f"Daily LLM request count {count} exceeded limit {self.daily_request_limit}"
                )
                raise BudgetExceededError(detail=detail)
            return int(count)

        # In-memory fallback
        current = self._memory_requests.get(key, 0) + 1
        self._memory_requests[key] = current
        if current > self.daily_request_limit:
            detail = f"Daily LLM request count {current} exceeded limit {self.daily_request_limit}"
            raise BudgetExceededError(detail=detail)
        return current

    async def record_tokens(self, tokens: int) -> int:
        """Record consumed tokens for reporting and telemetry."""
        if tokens <= 0:
            return 0
        key = self._today_key("tokens")

        if self._redis is not None:
            count = await self._redis.incrby(key, tokens)
            if count == tokens:
                await self._redis.expire(key, 172800)
            return int(count)

        current = self._memory_tokens.get(key, 0) + tokens
        self._memory_tokens[key] = current
        return current

    async def get_usage(self) -> dict[str, int]:
        """Return current request and token counts for today."""
        req_key = self._today_key("requests")
        tok_key = self._today_key("tokens")

        if self._redis is not None:
            req_raw = await self._redis.get(req_key)
            tok_raw = await self._redis.get(tok_key)
            return {
                "requests": int(req_raw) if req_raw else 0,
                "tokens": int(tok_raw) if tok_raw else 0,
            }

        return {
            "requests": self._memory_requests.get(req_key, 0),
            "tokens": self._memory_tokens.get(tok_key, 0),
        }
