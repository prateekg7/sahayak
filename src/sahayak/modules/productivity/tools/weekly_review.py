"""The 'weekly_review' MCP tool for cross-module weekly reports (T13.2)."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from sahayak.core.auth.principal import get_current_principal, requires
from sahayak.core.envelope import fail, ok
from sahayak.core.errors import AuthRequiredError, SahayakError
from sahayak.core.idempotency import idempotent
from sahayak.core.observability.instrumentation import instrument_tool
from sahayak.modules.productivity.service.weekly_review import WeeklyReviewService

logger = logging.getLogger(__name__)

_weekly_review_service: WeeklyReviewService | None = None


def set_weekly_review_service(service: WeeklyReviewService) -> None:
    """Inject the active WeeklyReviewService instance."""
    global _weekly_review_service
    _weekly_review_service = service


def get_weekly_review_service() -> WeeklyReviewService:
    """Retrieve the injected WeeklyReviewService instance."""
    if _weekly_review_service is None:
        raise RuntimeError("WeeklyReviewService has not been initialized.")
    return _weekly_review_service


class WeeklyReviewRequest(BaseModel):
    """Input payload for weekly review."""

    timezone: str = Field(default="UTC", description="IANA timezone name, e.g. 'Asia/Kolkata'.")
    request_id: str | None = Field(default=None, description="Optional idempotency key.")


WEEKLY_REVIEW_DESCRIPTION = (
    "Get a unified spoken weekly summary combining study, habits, spending, and health. "
    "Use when the user says 'Give me my weekly review', 'How was my week?', or 'Weekly report'. "
    "Do not use for today's morning overview; use daily_briefing instead."
)


@requires()
@idempotent(tool_name="weekly_review")
@instrument_tool("weekly_review", "productivity")
async def weekly_review(
    timezone: str = "UTC",
    request_id: str | None = None,
) -> dict[str, Any]:
    """Provide an adaptive cross-module weekly summary of study, habits, spending, and health."""
    principal = get_current_principal()
    if principal is None or principal.anonymous or principal.user_id is None:
        raise AuthRequiredError(
            spoken="Please link your account in the Alexa app to receive your weekly review.",
            detail="Account linking required for weekly_review tool",
        )

    try:
        req = WeeklyReviewRequest(timezone=timezone, request_id=request_id)
        service = get_weekly_review_service()

        spoken, summary_data, next_actions = await service.get_weekly_review(
            user_id=principal.user_id,
            timezone_str=req.timezone,
        )

        return ok(
            spoken_summary=spoken,
            data=summary_data.to_dict(),
            next_actions=next_actions,
            module="productivity",
            version="0.1.0",
        )
    except SahayakError as err:
        return fail(err, module="productivity", version="0.1.0")
    except Exception as exc:
        logger.exception("Unexpected error in weekly_review tool: %s", exc)
        return fail(SahayakError(), module="productivity", version="0.1.0")
