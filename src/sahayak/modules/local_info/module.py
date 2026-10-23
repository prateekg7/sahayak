"""Local and civic information module conforming to the Module protocol (T12.1, T12.2, T12.3)."""

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
            self._api = DefaultLocalInfoAPI(registered_count=2)
        return self._api

    def register_tools(self, mcp: Any, deps: Deps) -> None:
        """Register MCP tools for local and civic information."""
        self._deps = deps

        # Transit tool registration (T12.2)
        from sahayak.modules.local_info.adapters.transit import TransitHttpDataSource
        from sahayak.modules.local_info.service.transit import TransitService
        from sahayak.modules.local_info.tools.transit import (
            TRANSIT_STATUS_DESCRIPTION,
            set_transit_service,
            transit_status,
        )

        transit_source = TransitHttpDataSource(cache=deps.cache)
        transit_service = TransitService(data_source=transit_source)
        set_transit_service(transit_service)

        # Commodity prices tool registration (T12.3)
        from sahayak.modules.local_info.adapters.commodity import CommodityHttpDataSource
        from sahayak.modules.local_info.service.commodity import CommodityService
        from sahayak.modules.local_info.tools.commodity import (
            COMMODITY_PRICES_DESCRIPTION,
            commodity_prices,
            set_commodity_service,
        )

        commodity_source = CommodityHttpDataSource(cache=deps.cache)
        commodity_service = CommodityService(data_source=commodity_source)
        set_commodity_service(commodity_service)

        tool_decorator = getattr(mcp, "tool", None)
        if callable(tool_decorator):
            tool_decorator(name="transit_status", description=TRANSIT_STATUS_DESCRIPTION)(
                transit_status
            )
            tool_decorator(name="commodity_prices", description=COMMODITY_PRICES_DESCRIPTION)(
                commodity_prices
            )

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
