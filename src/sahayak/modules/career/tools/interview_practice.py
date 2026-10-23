"""The 'interview_practice' MCP tool for voice mock interviews and rubric feedback (T8.1)."""

from __future__ import annotations

import logging
from typing import Any

from sahayak.core.auth.principal import get_current_principal, requires
from sahayak.core.envelope import fail, ok
from sahayak.core.errors import AuthRequiredError, InvalidInputError, SahayakError
from sahayak.core.idempotency import idempotent
from sahayak.core.observability.instrumentation import instrument_tool
from sahayak.modules.career.schemas import InterviewRequest
from sahayak.modules.career.service.interview import InterviewService

logger = logging.getLogger(__name__)

_interview_service: InterviewService | None = None


def set_interview_service(service: InterviewService) -> None:
    """Inject the active InterviewService instance."""
    global _interview_service
    _interview_service = service


def get_interview_service() -> InterviewService:
    """Retrieve the injected InterviewService instance."""
    if _interview_service is None:
        raise RuntimeError("InterviewService has not been initialized.")
    return _interview_service


INTERVIEW_PRACTICE_DESCRIPTION = (
    "Conduct mock interview practice sessions with voice feedback and rubric scoring. "
    "Use when the user says 'Start a mock interview for Software Engineer', "
    "'Here is my answer to the interview question', 'Finish my interview session', "
    "or 'Show my interview practice history'. "
    "Do not use for logging daily tasks, expenses, or health metrics."
)


@requires()
@idempotent(tool_name="interview_practice")
@instrument_tool("interview_practice", "career")
async def interview_practice(
    action: str = "start",
    role: str | None = "Software Engineer",
    level: str | None = "mid",
    total_questions: int = 5,
    session_id: str | None = None,
    answer: str | None = None,
    limit: int = 5,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Execute mock interview actions: start, answer, finish, history."""
    principal = get_current_principal()
    if principal is None or principal.anonymous or principal.user_id is None:
        raise AuthRequiredError(
            spoken=(
                "Please link your account in the Alexa app to practice mock interviews "
                "and receive personalized feedback."
            ),
            detail="Account linking required for interview_practice tool",
        )

    try:
        req = InterviewRequest(
            action=action.strip().lower(),  # type: ignore[arg-type]
            role=role,
            level=level,
            total_questions=total_questions,
            session_id=session_id,
            answer=answer,
            limit=limit,
        )

        service = get_interview_service()

        if req.action == "start":
            data, spoken, next_actions = await service.start_session(
                user_id=principal.user_id,
                role=req.role or "Software Engineer",
                level=req.level or "mid",
                total_questions=req.total_questions,
            )
        elif req.action == "answer":
            if not req.session_id:
                raise InvalidInputError("Session ID is required to answer an interview question.")
            if not req.answer:
                raise InvalidInputError("Please provide an answer to evaluate.")
            data, spoken, next_actions = await service.answer_question(
                user_id=principal.user_id,
                session_id_str=req.session_id,
                answer=req.answer,
            )
        elif req.action == "finish":
            if not req.session_id:
                raise InvalidInputError("Session ID is required to finish an interview session.")
            data, spoken, next_actions = await service.finish_session(
                user_id=principal.user_id,
                session_id_str=req.session_id,
            )
        elif req.action == "history":
            data, spoken, next_actions = await service.get_history(
                user_id=principal.user_id,
                limit=req.limit,
            )
        else:
            raise InvalidInputError(
                f"Unknown action '{req.action}'. Expected start, answer, finish, or history."
            )

        return ok(
            spoken_summary=spoken,
            data=data,
            next_actions=next_actions,
            module="career",
            version="0.1.0",
        )
    except SahayakError as err:
        return fail(err, module="career", version="0.1.0")
    except Exception as exc:
        logger.exception("Unexpected error in interview_practice tool: %s", exc)
        return fail(SahayakError(), module="career", version="0.1.0")
