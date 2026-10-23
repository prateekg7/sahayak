"""MCP tool exposing learning progress, study streaks, and weak-topic analytics (T3.13)."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from sahayak.core.auth.principal import Principal, get_current_principal, requires
from sahayak.core.envelope import fail, ok
from sahayak.core.errors import AuthRequiredError, InvalidInputError, SahayakError
from sahayak.core.observability.instrumentation import instrument_tool
from sahayak.modules.academics.schemas import ProgressReportRequest
from sahayak.modules.academics.service.progress import ProgressService

PROGRESS_REPORT_DESCRIPTION = (
    "Inspect academic quiz performance, study streaks, weak topics, and weekly summaries. "
    "Use when the student asks 'How am I doing?', 'What are my weak topics?', "
    "'What is my streak?', or 'How did I do this week?'. "
    "Do not use for starting quizzes or scheduling study plans; "
    "use 'quiz_start' or 'study_plan' instead."
)

_progress_service: ProgressService | None = None


def set_progress_service(service: ProgressService | None) -> None:
    """Configure module-level progress service instance."""
    global _progress_service
    _progress_service = service


def get_progress_service() -> ProgressService:
    """Retrieve the configured progress service instance."""
    if _progress_service is None:
        raise RuntimeError("ProgressService has not been initialized.")
    return _progress_service


@requires()
async def progress_report(
    scope: str = "summary",
    timezone: str = "UTC",
) -> dict[str, Any]:
    """Report student quiz performance, study streak, weak topics, or weekly activity."""
    async with instrument_tool("progress_report", "academics"):
        principal: Principal = get_current_principal()
        if principal.anonymous or principal.user_id is None:
            return fail(
                AuthRequiredError(
                    spoken=(
                        "Please link your account in the Alexa app to view your learning progress."
                    ),
                    detail="progress_report requires an authenticated platform user",
                ),
                module="academics",
                version="0.1.0",
            )

        if isinstance(scope, ProgressReportRequest):
            req = scope
        else:
            try:
                req = ProgressReportRequest(
                    scope=scope,  # type: ignore[arg-type]
                    timezone=timezone,
                )
            except (ValidationError, ValueError) as val_err:
                return fail(
                    InvalidInputError(
                        spoken=(
                            "Please choose a valid report scope: summary, weak topics, "
                            "streak, or weekly."
                        ),
                        detail=str(val_err),
                    ),
                    module="academics",
                    version="0.1.0",
                )

        service = get_progress_service()

        try:
            spoken, data, next_actions = await service.get_progress_report(
                user_id=principal.user_id,
                scope=req.scope,
                user_timezone=req.timezone,
            )

            return ok(
                spoken_summary=spoken,
                data=data.model_dump(),
                next_actions=next_actions,
                module="academics",
                version="0.1.0",
            )
        except SahayakError as err:
            return fail(err, module="academics", version="0.1.0")
