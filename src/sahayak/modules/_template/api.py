"""Public API published by the template module for cross-module calls."""

from __future__ import annotations

from typing import Protocol


class TemplateModuleAPI(Protocol):
    """Methods exposed to other modules."""

    async def get_ping_count(self) -> int:
        """Return the number of pings processed by the template module."""
        ...
