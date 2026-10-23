"""MCP tool for creating and managing exam study plans."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sahayak.core.auth.principal import get_current_principal, requires
from sahayak.core.config import get_settings
from sahayak.core.envelope import fail, ok
from sahayak.core.errors import InvalidInputError, SahayakError
from sahayak.core.idempotency import idempotent
from sahayak.core.observability.instrumentation import instrument_tool
from sahayak.modules.academics.schemas import (
    StudyPlanRequest,
)
from sahayak.modules.academics.service.plan import StudyPlanService

logger = logging.getLogger(__name__)

STUDY_PLAN_DESCRIPTION = (
    "Creates and manages day-by-day exam preparation schedules and daily study tasks. "
    "Use when the user wants to prepare for an upcoming exam or ask what to study today, "
    "such as 'Alexa, make a study plan for chemistry exam on the 15th' or "
    "'Alexa, what should I study today?'. "
    "Do not use for practicing flashcards or quizzes; use flashcards or quiz_start instead."
)

_study_plan_service: StudyPlanService | None = None


def set_study_plan_service(service: StudyPlanService | None) -> None:
    """Set or override the module-level study plan service instance."""
    global _study_plan_service
    _study_plan_service = service


def get_study_plan_service() -> StudyPlanService:
    """Return the configured study plan service instance or lazily initialize one."""
    global _study_plan_service
    if _study_plan_service is None:
        settings = get_settings()
        from sahayak.core.db.session import create_engine, create_session_factory

        engine = create_engine(settings)
        session_factory = create_session_factory(engine)
        _study_plan_service = StudyPlanService(session_factory=session_factory)
    return _study_plan_service


@requires()
@idempotent(tool_name="study_plan")
async def study_plan(
    action: str,
    goal: str | None = None,
    exam_date: str | None = None,
    topics: list[str] | None = None,
    hours_per_day: float = 1.0,
    timezone: str = "UTC",
    plan_id: str | None = None,
    task_id: str | None = None,
    mark_done: bool | None = None,
    replan: bool = False,
    limit: int = 5,
    request_id: str = "",
) -> dict[str, Any]:
    """Create, view, update, and list exam study plans and daily tasks."""
    if request_id:
        from sahayak.core.request_id import set_request_id

        set_request_id(request_id)

    async with instrument_tool("study_plan", "academics"):
        service = get_study_plan_service()
        principal = get_current_principal()
        user_id = principal.user_id
        if user_id is None:
            from sahayak.core.errors import AuthRequiredError

            return fail(AuthRequiredError(), module="academics", version="0.1.0")

        try:
            req = StudyPlanRequest(
                action=action,  # type: ignore[arg-type]
                goal=goal,
                exam_date=exam_date,
                topics=topics,
                hours_per_day=hours_per_day,
                timezone=timezone,
                plan_id=plan_id,
                task_id=task_id,
                mark_done=mark_done,
                replan=replan,
                limit=limit,
                request_id=request_id or None,
            )
        except Exception as val_err:
            return fail(
                InvalidInputError(
                    spoken=(
                        "Please provide a valid study plan action "
                        "like create, today, update, or list."
                    ),
                    detail=str(val_err),
                ),
                module="academics",
                version="0.1.0",
            )

        try:
            if req.action == "create":
                if not req.goal or not req.goal.strip():
                    raise InvalidInputError(
                        spoken=(
                            "Please specify a subject or goal for your "
                            "study plan, like chemistry exam."
                        ),
                        detail="Missing goal for study plan",
                    )
                if not req.exam_date or not req.exam_date.strip():
                    raise InvalidInputError(
                        spoken=(
                            "Please specify an upcoming exam date, like on the 15th or in 2 weeks."
                        ),
                        detail="Missing exam_date for study plan",
                    )

                data, spoken = await service.create_study_plan(
                    user_id=user_id,
                    goal=req.goal,
                    exam_date_str=req.exam_date,
                    topics=req.topics,
                    hours_per_day=req.hours_per_day,
                    timezone=req.timezone,
                )
                return ok(
                    spoken_summary=spoken,
                    data=data.model_dump(),
                    next_actions=["Say 'what should I study today' to check your schedule."],
                    module="academics",
                    version="0.1.0",
                )

            elif req.action == "today":
                plan_uuid: uuid.UUID | None = None
                if req.plan_id:
                    try:
                        plan_uuid = uuid.UUID(req.plan_id)
                    except ValueError as err:
                        raise InvalidInputError(
                            spoken="The provided study plan ID is invalid.",
                            detail=str(err),
                        ) from err

                data, spoken = await service.get_today_tasks(
                    user_id=user_id,
                    plan_id=plan_uuid,
                    timezone=req.timezone,
                )
                return ok(
                    spoken_summary=spoken,
                    data=data.model_dump(),
                    next_actions=["Say 'mark done' when you finish a study task."],
                    module="academics",
                    version="0.1.0",
                )

            elif req.action == "update":
                plan_uuid = None
                if req.plan_id:
                    try:
                        plan_uuid = uuid.UUID(req.plan_id)
                    except ValueError as err:
                        raise InvalidInputError(
                            spoken="The provided study plan ID is invalid.",
                            detail=str(err),
                        ) from err

                task_uuid: uuid.UUID | None = None
                if req.task_id:
                    try:
                        task_uuid = uuid.UUID(req.task_id)
                    except ValueError as err:
                        raise InvalidInputError(
                            spoken="The provided task ID is invalid.",
                            detail=str(err),
                        ) from err

                data, spoken = await service.update_plan(
                    user_id=user_id,
                    plan_id=plan_uuid,
                    task_id=task_uuid,
                    mark_done=req.mark_done,
                    replan=req.replan,
                    hours_per_day=req.hours_per_day,
                    timezone=req.timezone,
                )
                return ok(
                    spoken_summary=spoken,
                    data=data.model_dump(),
                    next_actions=["Say 'what should I study today' to view your updated tasks."],
                    module="academics",
                    version="0.1.0",
                )

            elif req.action == "list":
                data, spoken = await service.list_plans(
                    user_id=user_id,
                    limit=req.limit,
                )
                return ok(
                    spoken_summary=spoken,
                    data=data.model_dump(),
                    next_actions=["Say 'what should I study today' to view today's tasks."],
                    module="academics",
                    version="0.1.0",
                )

            else:
                raise InvalidInputError(
                    spoken="Unknown study plan action.",
                    detail=f"Unsupported action '{req.action}'",
                )

        except SahayakError as exc:
            return fail(exc, module="academics", version="0.1.0")
        except Exception as exc:
            logger.exception("Unexpected error in study_plan tool: %s", exc)
            return fail(
                InvalidInputError(
                    spoken="I encountered an issue with your study plan. Please try again.",
                    detail=str(exc),
                ),
                module="academics",
                version="0.1.0",
            )
