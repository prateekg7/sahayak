"""The 'health_summary' MCP tool for periodic health reports and medicine adherence (T7.2)."""

from __future__ import annotations

import logging
from typing import Any

from sahayak.core.auth.principal import get_current_principal, requires
from sahayak.core.envelope import fail, ok
from sahayak.core.errors import AuthRequiredError, SahayakError
from sahayak.core.idempotency import idempotent
from sahayak.core.observability.instrumentation import instrument_tool
from sahayak.modules.health.schemas import (
    HealthSummaryAction,
    HealthSummaryRequest,
)
from sahayak.modules.health.service.health_summary import HealthSummaryService

logger = logging.getLogger(__name__)

_health_summary_service: HealthSummaryService | None = None


def set_health_summary_service(service: HealthSummaryService) -> None:
    """Inject the active HealthSummaryService instance."""
    global _health_summary_service
    _health_summary_service = service


def get_health_summary_service() -> HealthSummaryService:
    """Retrieve the injected HealthSummaryService instance."""
    if _health_summary_service is None:
        raise RuntimeError("HealthSummaryService has not been initialized.")
    return _health_summary_service


HEALTH_SUMMARY_DESCRIPTION = (
    "Review daily health summaries, weekly adherence averages, and manage medicine schedules. "
    "Use when the user asks 'What is my health summary today?', 'How was my health this week?', "
    "'What medicines are due today?', 'Mark my vitamin as taken', or 'Add pill to my schedule'. "
    "Do not use for logging individual water, meals, or workouts (use health_log), "
    "or for clinical medical diagnosis or dosing instructions."
)


@requires()
@idempotent(tool_name="health_summary")
@instrument_tool("health_summary", "health")
async def health_summary(
    action: str = "today",
    medicine_name: str | None = None,
    scheduled_time: str | None = None,
    dosage_text: str | None = "1 dose",
    times: list[str] | None = None,
    days: list[str] | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Execute periodic health summaries or medicine schedule operations."""
    principal = get_current_principal()
    if principal is None or principal.anonymous or principal.user_id is None:
        raise AuthRequiredError(
            spoken=(
                "Please link your account in the Alexa app to view your health "
                "summaries and medicine schedules."
            ),
            detail="Account linking required for health_summary tool",
        )

    try:
        req = HealthSummaryRequest(
            action=HealthSummaryAction(action.strip().lower()),
            medicine_name=medicine_name,
            scheduled_time=scheduled_time,
            dosage_text=dosage_text,
            times=times,
            days=days,
            request_id=request_id,
        )

        service = get_health_summary_service()
        data, spoken = await service.execute(user_id=principal.user_id, request=req)

        next_actions = [
            "health_summary(action='today')",
            "health_summary(action='week')",
            "health_summary(action='medicines_due')",
        ]

        return ok(
            spoken_summary=spoken,
            data=data.model_dump(),
            next_actions=next_actions,
            module="health",
            version="0.1.0",
        )
    except SahayakError as err:
        return fail(err, module="health", version="0.1.0")
    except Exception as exc:
        logger.exception("Unexpected error in health_summary tool: %s", exc)
        return fail(SahayakError(), module="health", version="0.1.0")
