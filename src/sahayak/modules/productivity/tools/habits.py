"""The 'habits' MCP tool for tracking daily habits and streak metrics (T5.2)."""

from __future__ import annotations

import logging
from typing import Any

from sahayak.core.auth.principal import get_current_principal, requires
from sahayak.core.envelope import fail, ok
from sahayak.core.errors import AuthRequiredError, InvalidInputError, SahayakError
from sahayak.core.idempotency import idempotent
from sahayak.core.observability.instrumentation import instrument_tool
from sahayak.modules.productivity.schemas import HabitAction, HabitsRequest
from sahayak.modules.productivity.service.habits import HabitService

logger = logging.getLogger(__name__)

_habit_service: HabitService | None = None


def set_habit_service(service: HabitService) -> None:
    """Inject the active HabitService instance."""
    global _habit_service
    _habit_service = service


def get_habit_service() -> HabitService:
    """Retrieve the injected HabitService instance."""
    if _habit_service is None:
        raise RuntimeError("HabitService has not been initialized.")
    return _habit_service


HABITS_DESCRIPTION = (
    "Track daily habits, log completions, and monitor streaks over time. "
    "Use when the user wants to manage recurring routines or check streaks, such as "
    "'Alexa, log meditation', 'Track a habit: read 20 pages', or 'What is my habit streak?'. "
    "Do not use for one-time to-do list tasks or deadlines; use the tasks tool instead."
)


@requires()
@idempotent(tool_name="habits")
@instrument_tool("habits", "productivity")
async def habits(
    action: str,
    name: str | None = None,
    habit_id: str | None = None,
    frequency: str = "daily",
    date: str | None = None,
    timezone: str = "UTC",
    request_id: str | None = None,
) -> dict[str, Any]:
    """Execute habit management operations (create, log, status, list)."""
    principal = get_current_principal()
    if principal is None or principal.anonymous or principal.user_id is None:
        raise AuthRequiredError(
            spoken="Please link your account in the Alexa app to manage habits.",
            detail="Account linking required for habits tool",
        )

    try:
        req = HabitsRequest(
            action=HabitAction(action.strip().lower()),
            name=name,
            habit_id=habit_id,
            frequency=frequency,
            date=date,
            timezone=timezone,
            request_id=request_id,
        )

        service = get_habit_service()

        if req.action == HabitAction.CREATE:
            spoken, data, next_actions = await service.create_habit(
                user_id=principal.user_id,
                name=req.name,
                frequency=req.frequency,
            )
        elif req.action == HabitAction.LOG:
            spoken, data, next_actions = await service.log_habit(
                user_id=principal.user_id,
                name=req.name,
                habit_id_str=req.habit_id,
                date_str=req.date,
                timezone_str=req.timezone,
            )
        elif req.action == HabitAction.STATUS:
            spoken, data, next_actions = await service.get_habit_status(
                user_id=principal.user_id,
                name=req.name,
                habit_id_str=req.habit_id,
                timezone_str=req.timezone,
            )
        elif req.action == HabitAction.LIST:
            spoken, data, next_actions = await service.list_habits(
                user_id=principal.user_id,
                timezone_str=req.timezone,
            )
        else:
            raise InvalidInputError(
                spoken=f"Unsupported habit action {req.action}.",
                detail=f"Unsupported habit action '{req.action}'",
            )

        return ok(
            spoken_summary=spoken,
            data=data.model_dump(),
            next_actions=next_actions,
            module="productivity",
            version="0.1.0",
        )
    except SahayakError as err:
        return fail(err, module="productivity", version="0.1.0")
    except Exception as exc:
        logger.exception("Unexpected error in habits tool: %s", exc)
        return fail(SahayakError(), module="productivity", version="0.1.0")
