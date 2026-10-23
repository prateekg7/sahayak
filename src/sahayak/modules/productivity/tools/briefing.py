"""The 'daily_briefing' MCP tool for a unified overview of the day (T5.5)."""

from __future__ import annotations

import logging
from typing import Any

from sahayak.core.auth.principal import get_current_principal, requires
from sahayak.core.envelope import fail, ok
from sahayak.core.errors import AuthRequiredError, SahayakError
from sahayak.core.idempotency import idempotent
from sahayak.core.observability.instrumentation import instrument_tool
from sahayak.modules.productivity.schemas import DailyBriefingRequest
from sahayak.modules.productivity.service.briefing import BriefingService

logger = logging.getLogger(__name__)

_briefing_service: BriefingService | None = None


def set_briefing_service(service: BriefingService) -> None:
    """Inject the active BriefingService instance."""
    global _briefing_service
    _briefing_service = service


def get_briefing_service() -> BriefingService:
    """Retrieve the injected BriefingService instance."""
    if _briefing_service is None:
        raise RuntimeError("BriefingService has not been initialized.")
    return _briefing_service


DAILY_BRIEFING_DESCRIPTION = (
    "Get a unified spoken summary of your day including tasks, habits, and study goals. "
    "Use when the user says 'Give me my daily briefing', 'What does my day look like?', "
    "or 'Good morning sahayak'. "
    "Do not use for creating individual tasks or habits; use tasks or habits instead."
)


@requires()
@idempotent(tool_name="daily_briefing")
@instrument_tool("daily_briefing", "productivity")
async def daily_briefing(
    timezone: str = "UTC",
    request_id: str | None = None,
) -> dict[str, Any]:
    """Provide an ordered, concise daily briefing of tasks, habits, and study goals."""
    principal = get_current_principal()
    if principal is None or principal.anonymous or principal.user_id is None:
        raise AuthRequiredError(
            spoken="Please link your account in the Alexa app to receive your daily briefing.",
            detail="Account linking required for daily_briefing tool",
        )

    try:
        req = DailyBriefingRequest(timezone=timezone)
        service = get_briefing_service()

        spoken, data, next_actions = await service.get_daily_briefing(
            user_id=principal.user_id,
            timezone_str=req.timezone,
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
        logger.exception("Unexpected error in daily_briefing tool: %s", exc)
        return fail(SahayakError(), module="productivity", version="0.1.0")
