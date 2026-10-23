"""The 'health_log' MCP tool for personal health metric logging (T7.1)."""

from __future__ import annotations

import logging
from typing import Any

from sahayak.core.auth.principal import get_current_principal, requires
from sahayak.core.envelope import fail, ok
from sahayak.core.errors import AuthRequiredError, SahayakError
from sahayak.core.idempotency import idempotent
from sahayak.core.observability.instrumentation import instrument_tool
from sahayak.modules.health.schemas import (
    HealthLogAction,
    HealthLogRequest,
)
from sahayak.modules.health.service.health_log import HealthLogService

logger = logging.getLogger(__name__)

_health_log_service: HealthLogService | None = None


def set_health_log_service(service: HealthLogService) -> None:
    """Inject the active HealthLogService instance."""
    global _health_log_service
    _health_log_service = service


def get_health_log_service() -> HealthLogService:
    """Retrieve the injected HealthLogService instance."""
    if _health_log_service is None:
        raise RuntimeError("HealthLogService has not been initialized.")
    return _health_log_service


HEALTH_LOG_DESCRIPTION = (
    "Log personal health metrics such as water, meals, workouts, sleep, and weight. "
    "Use when the user says 'Log 500 ml of water', 'I had oatmeal for breakfast', "
    "'Log 30 minutes of running', 'I slept 7 hours', or 'Undo my last water entry'. "
    "Do not use for medical diagnosis, prescriptions, or clinical advice; "
    "this tool is for personal activity logging only."
)


@requires()
@idempotent(tool_name="health_log")
@instrument_tool("health_log", "health")
async def health_log(
    action: str = "log",
    kind: str | None = None,
    value: float | int | str | None = None,
    unit: str | None = None,
    meal_name: str | None = None,
    meal_type: str | None = None,
    activity: str | None = None,
    duration: float | int | str | None = None,
    intensity: str | None = None,
    calories: int | str | None = None,
    notes: str | None = None,
    entry_id: str | None = None,
    limit: int = 5,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Execute personal health metric logging operations (log, list, undo_last)."""
    principal = get_current_principal()
    if principal is None or principal.anonymous or principal.user_id is None:
        raise AuthRequiredError(
            spoken=(
                "Please link your account in the Alexa app to log and view "
                "your personal health metrics."
            ),
            detail="Account linking required for health_log tool",
        )

    try:
        req = HealthLogRequest(
            action=HealthLogAction(action.strip().lower()),
            kind=kind,
            value=value,
            unit=unit,
            meal_name=meal_name,
            meal_type=meal_type,
            activity=activity,
            duration=duration,
            intensity=intensity,
            calories=calories,
            notes=notes,
            entry_id=entry_id,
            limit=limit,
            request_id=request_id,
        )

        service = get_health_log_service()
        data, spoken = await service.execute(user_id=principal.user_id, request=req)

        next_actions = ["health_log(action='list')", "health_log(action='undo_last')"]
        if req.action == HealthLogAction.LOG and req.kind:
            next_actions = [
                f"health_log(action='list', kind='{req.kind}')",
                f"health_log(action='undo_last', kind='{req.kind}')",
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
        logger.exception("Unexpected error in health_log tool: %s", exc)
        return fail(SahayakError(), module="health", version="0.1.0")
