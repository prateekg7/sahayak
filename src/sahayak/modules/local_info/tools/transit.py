"""MCP tool for real-time transit departures, line status, and delay alerts (T12.2)."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from sahayak.core.auth.principal import allow_anonymous
from sahayak.core.envelope import fail, ok
from sahayak.core.errors import InvalidInputError, SahayakError
from sahayak.core.observability.instrumentation import instrument_tool
from sahayak.modules.local_info.schemas import TransitStatusRequest
from sahayak.modules.local_info.service.transit import TransitService

TRANSIT_STATUS_DESCRIPTION = (
    "Check real-time train and metro departures, line delays, and service status. "
    "Use when the user asks 'When is the next train from Rajiv Chowk?', "
    "'What is the status of the Yellow line?', or 'Next departures from CP'. "
    "Do not use for checking mandi agricultural prices or government welfare schemes; "
    "use 'commodity_prices' or 'scheme_finder' instead."
)

_transit_service: TransitService | None = None


def set_transit_service(service: TransitService | None) -> None:
    """Configure module-level transit service instance."""
    global _transit_service
    _transit_service = service


def get_transit_service() -> TransitService:
    """Retrieve the configured transit service instance."""
    global _transit_service
    if _transit_service is None:
        _transit_service = TransitService()
    return _transit_service


@allow_anonymous
async def transit_status(
    action: str = "next_departures",
    station: str | None = None,
    line: str | None = None,
    destination: str | None = None,
) -> dict[str, Any]:
    """Check real-time metro and train departures and operational line status."""
    async with instrument_tool("transit_status", "local_info"):
        try:
            req = TransitStatusRequest(
                action=action,  # type: ignore[arg-type]
                station=station,
                line=line,
                destination=destination,
            )
        except (ValidationError, ValueError) as err:
            return fail(
                InvalidInputError(
                    spoken=(
                        "Please specify an action of next_departures or status, "
                        "and provide a station name if checking departures."
                    ),
                    detail=str(err),
                ),
                module="local_info",
                version="0.1.0",
            )

        service = get_transit_service()

        try:
            if req.action == "next_departures":
                if not req.station:
                    return fail(
                        InvalidInputError(
                            spoken=(
                                "Please specify which station you want departures for, "
                                "such as Rajiv Chowk or Hauz Khas."
                            ),
                            detail="Station is required when action is 'next_departures'.",
                        ),
                        module="local_info",
                        version="0.1.0",
                    )
                spoken, data = await service.get_next_departures(
                    station_query=req.station,
                    line_filter=req.line,
                    destination_filter=req.destination,
                )
                next_actions = ["check line status", "check another station"]
            elif req.action == "status":
                spoken, data = await service.get_line_status(line_filter=req.line)
                next_actions = ["check departures", "check another line"]
            else:
                return fail(
                    InvalidInputError(
                        spoken="Action must be next_departures or status.",
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
