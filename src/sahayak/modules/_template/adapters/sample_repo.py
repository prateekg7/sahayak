"""Repository adapter implementing PingRepositoryPort in-memory / storage."""

from __future__ import annotations

from sahayak.modules._template.ports import PingRepositoryPort


class InMemoryPingRepository(PingRepositoryPort):
    """In-memory adapter used for tests and lightweight default runtime."""

    def __init__(self) -> None:
        self._pings: list[str] = []

    async def record_ping(self, message: str) -> None:
        self._pings.append(message)

    async def get_ping_count(self) -> int:
        return len(self._pings)
