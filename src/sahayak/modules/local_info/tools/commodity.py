"""MCP tool for agricultural mandi crop prices, comparisons, and market trends (T12.3)."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from sahayak.core.auth.principal import allow_anonymous
from sahayak.core.envelope import fail, ok
from sahayak.core.errors import InvalidInputError, SahayakError
from sahayak.core.observability.instrumentation import instrument_tool
from sahayak.modules.local_info.schemas import CommodityPriceRequest
from sahayak.modules.local_info.service.commodity import CommodityService

COMMODITY_PRICES_DESCRIPTION = (
    "Check daily agricultural mandi crop prices, wholesale market comparisons, and trends. "
    "Use when the user asks 'What is the wheat price in Azadpur mandi?', "
    "'Compare onion prices between Azadpur and Ghazipur', or 'Is tomato price increasing?'. "
    "Do not use for tracking train schedules or finding welfare schemes; "
    "use 'transit_status' or 'scheme_finder' instead."
)

_commodity_service: CommodityService | None = None


def set_commodity_service(service: CommodityService | None) -> None:
    """Configure module-level commodity service instance."""
    global _commodity_service
    _commodity_service = service


def get_commodity_service() -> CommodityService:
    """Retrieve the configured commodity service instance."""
    global _commodity_service
    if _commodity_service is None:
        _commodity_service = CommodityService()
    return _commodity_service


@allow_anonymous
async def commodity_prices(
    action: str = "get_price",
    commodity: str | None = None,
    market: str | None = None,
    markets: list[str] | None = None,
) -> dict[str, Any]:
    """Check wholesale crop prices, compare mandis, and analyze agricultural trends."""
    async with instrument_tool("commodity_prices", "local_info"):
        try:
            req = CommodityPriceRequest(
                action=action,  # type: ignore[arg-type]
                commodity=commodity,
                market=market,
                markets=markets,
            )
        except (ValidationError, ValueError) as err:
            return fail(
                InvalidInputError(
                    spoken=(
                        "Please specify an action of get_price, compare_markets, or trend, "
                        "and provide a crop name."
                    ),
                    detail=str(err),
                ),
                module="local_info",
                version="0.1.0",
            )

        if not req.commodity:
            return fail(
                InvalidInputError(
                    spoken=(
                        "Please specify which crop you want prices for, "
                        "such as wheat, onion, or tomato."
                    ),
                    detail="Commodity name is required.",
                ),
                module="local_info",
                version="0.1.0",
            )

        service = get_commodity_service()

        try:
            if req.action == "get_price":
                spoken, data = await service.get_price(
                    commodity_query=req.commodity,
                    market_query=req.market,
                )
                next_actions = ["compare markets", "check price trend"]
            elif req.action == "compare_markets":
                m_list = req.markets or ([req.market] if req.market else [])
                spoken, data = await service.compare_markets(
                    commodity_query=req.commodity,
                    market_queries=m_list,
                )
                next_actions = ["check price in single mandi", "check price trend"]
            elif req.action == "trend":
                spoken, data = await service.get_trend(
                    commodity_query=req.commodity,
                    market_query=req.market,
                )
                next_actions = ["get today's price", "compare other mandis"]
            else:
                return fail(
                    InvalidInputError(
                        spoken="Action must be get_price, compare_markets, or trend.",
                        detail=f"Unknown action {req.action}",
                    ),
                    module="local_info",
                    version="0.1.0",
                )

            return ok(
                spoken_summary=spoken,
                data=data,
                next_actions=next_actions,
                module="local_info",
                version="0.1.0",
            )
        except SahayakError as err:
            return fail(err, module="local_info", version="0.1.0")
