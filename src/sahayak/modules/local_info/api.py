"""Public API interface for cross-module local_info access (T12.1)."""

from __future__ import annotations

from typing import Protocol


class LocalInfoAPI(Protocol):
    """Public contract that other modules can consume without internal imports."""

    async def get_registered_sources_count(self) -> int:
        """Return the number of configured external data sources."""
        ...


class DefaultLocalInfoAPI:
    """Default implementation of LocalInfoAPI."""

    def __init__(self, registered_count: int = 0) -> None:
        self._count = registered_count

    async def get_registered_sources_count(self) -> int:
        return self._count
