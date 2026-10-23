"""Local and civic information module conforming to the Module protocol (T12.1)."""

from __future__ import annotations

from typing import Any

from sahayak.core.module import Deps, HealthStatus
from sahayak.modules.local_info.api import DefaultLocalInfoAPI, LocalInfoAPI


class LocalInfoModule:
    """Local and civic info module integrating external transit, mandi, and civic APIs."""

    def __init__(self) -> None:
        self._deps: Deps | None = None
        self._api: LocalInfoAPI | None = None

    @property
    def name(self) -> str:
        return "local_info"

    @property
    def version(self) -> str:
        return "0.1.0"

    @property
    def api(self) -> LocalInfoAPI:
        if self._api is None:
            self._api = DefaultLocalInfoAPI(registered_count=0)
        return self._api

    def register_tools(self, mcp: Any, deps: Deps) -> None:
        """Register MCP tools for local and civic information."""
        self._deps = deps
        # Tools will be registered in T12.2 (transit), T12.3 (prices), T12.4 (schemes)

    def register_jobs(self, worker: Any) -> None:
        """Register background worker jobs for local_info module."""
        pass

    def migrations_path(self) -> str | None:
        """Local info relies on external data sources and in-memory/Redis caches."""
        return None

    def health(self) -> HealthStatus:
        return HealthStatus(healthy=True, detail="Local info module is operational")

    def on_event(self, event: Any) -> None:
        """Dispatched domain events hook."""
        pass

    async def export_user_data(self, user_id: str) -> dict[str, Any]:
        """GDPR Right to Access: local info provides public civic data."""
        return {}

    async def delete_user_data(self, user_id: str) -> None:
        """GDPR Right to Erasure: local info stores no user-scoped persistent PII."""
        pass


module = LocalInfoModule()
