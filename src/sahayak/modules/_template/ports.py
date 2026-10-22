"""Ports (interfaces) required by the template module domain and services.

Adapters implement these protocols to provide concrete I/O or storage.
"""

from __future__ import annotations

from typing import Protocol


class PingRepositoryPort(Protocol):
    """Abstract persistence port for ping audit records."""

    async def record_ping(self, message: str) -> None:
        """Persist a record of a received ping."""
        ...

    async def get_ping_count(self) -> int:
        """Return the number of recorded pings."""
        ...
