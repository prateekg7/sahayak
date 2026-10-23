"""The 'focus_timer' MCP tool for Pomodoro focus sessions and history (T5.4)."""

from __future__ import annotations

import logging
from typing import Any

from sahayak.core.auth.principal import get_current_principal, requires
from sahayak.core.envelope import fail, ok
from sahayak.core.errors import AuthRequiredError, InvalidInputError, SahayakError
from sahayak.core.idempotency import idempotent
from sahayak.core.observability.instrumentation import instrument_tool
from sahayak.modules.productivity.schemas import FocusAction, FocusRequest
from sahayak.modules.productivity.service.focus import FocusService

logger = logging.getLogger(__name__)

_focus_service: FocusService | None = None


def set_focus_service(service: FocusService) -> None:
    """Inject the active FocusService instance."""
    global _focus_service
    _focus_service = service


def get_focus_service() -> FocusService:
    """Retrieve the injected FocusService instance."""
    if _focus_service is None:
        raise RuntimeError("FocusService has not been initialized.")
    return _focus_service


FOCUS_TIMER_DESCRIPTION = (
    "Run Pomodoro focus sessions, check remaining time, and view completion history. "
    "Use when the user says 'Start a 25 minute focus session', "
    "'How much time is left on my timer?', "
    "'Stop focus timer', or 'Show my focus history'. "
    "Do not use for to-do task management; use the tasks tool instead."
)


@requires()
@idempotent(tool_name="focus_timer")
@instrument_tool("focus_timer", "productivity")
async def focus_timer(
    action: str,
    duration_minutes: int = 25,
    task_label: str | None = None,
    limit: int = 10,
    timezone: str = "UTC",
    request_id: str | None = None,
) -> dict[str, Any]:
    """Execute focus timer operations (start, status, stop, history)."""
    principal = get_current_principal()
    if principal is None or principal.anonymous or principal.user_id is None:
        raise AuthRequiredError(
            spoken="Please link your account in the Alexa app to use the focus timer.",
            detail="Account linking required for focus_timer tool",
        )

    try:
        req = FocusRequest(
            action=FocusAction(action.strip().lower()),
            duration_minutes=duration_minutes,
            task_label=task_label,
            limit=limit,
            timezone=timezone,
            request_id=request_id,
        )

        service = get_focus_service()

        if req.action == FocusAction.START:
            spoken, data, next_actions = await service.start_session(
                user_id=principal.user_id,
                duration_minutes=req.duration_minutes,
                task_label=req.task_label,
            )
        elif req.action == FocusAction.STATUS:
            spoken, data, next_actions = await service.get_session_status(
                user_id=principal.user_id,
            )
        elif req.action == FocusAction.STOP:
            spoken, data, next_actions = await service.stop_session(
                user_id=principal.user_id,
            )
        elif req.action == FocusAction.HISTORY:
            spoken, data, next_actions = await service.get_history(
                user_id=principal.user_id,
                limit=req.limit,
                timezone_str=req.timezone,
            )
        else:
            raise InvalidInputError(
                spoken=f"Unsupported action {req.action}.",
                detail=f"Unsupported focus timer action '{req.action}'",
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
        logger.exception("Unexpected error in focus_timer tool: %s", exc)
        return fail(SahayakError(), module="productivity", version="0.1.0")
