"""The 'career_practice' MCP tool for resume bullet polishing and daily questions (T8.3)."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from sahayak.core.auth.principal import get_current_principal, requires
from sahayak.core.envelope import fail, ok
from sahayak.core.errors import AuthRequiredError, InvalidInputError, SahayakError
from sahayak.core.idempotency import idempotent
from sahayak.core.observability.instrumentation import instrument_tool
from sahayak.modules.career.schemas import CareerPracticeRequest
from sahayak.modules.career.service.practice import CareerPracticeService

logger = logging.getLogger(__name__)

_practice_service: CareerPracticeService | None = None


def set_practice_service(service: CareerPracticeService) -> None:
    """Inject the active CareerPracticeService instance."""
    global _practice_service
    _practice_service = service


def get_practice_service() -> CareerPracticeService:
    """Retrieve the injected CareerPracticeService instance."""
    if _practice_service is None:
        raise RuntimeError("CareerPracticeService has not been initialized.")
    return _practice_service


CAREER_PRACTICE_DESCRIPTION = (
    "Improve resume bullet points using the XYZ formula and answer daily career questions. "
    "Use when the user says 'Improve my resume bullet: led migration of database', "
    "'Give me today's career practice question', or 'Check my answer to the daily question'. "
    "Do not use for conducting full mock interview sessions or logging job applications."
)


@requires()
@idempotent(tool_name="career_practice")
@instrument_tool("career_practice", "career")
async def career_practice(
    action: str = "daily_question",
    bullet: str | None = None,
    question_key: str | None = None,
    answer: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Execute career practice operations: improve_bullet, daily_question, check_answer."""
    principal = get_current_principal()
    if principal is None or principal.anonymous or principal.user_id is None:
        raise AuthRequiredError(
            spoken=(
                "Please link your account in the Alexa app to practice career questions "
                "and polish your resume bullets."
            ),
            detail="Account linking required for career_practice tool",
        )

    try:
        try:
            req = CareerPracticeRequest(
                action=action.strip().lower(),  # type: ignore[arg-type]
                bullet=bullet,
                question_key=question_key,
                answer=answer,
            )
        except (ValidationError, ValueError) as val_err:
            raise InvalidInputError(
                spoken=(
                    "Please choose a valid action: improve_bullet, daily_question, or check_answer."
                ),
                detail=str(val_err),
            ) from val_err

        service = get_practice_service()

        if req.action == "improve_bullet":
            if not req.bullet:
                raise InvalidInputError("Please provide a bullet point to improve.")
            data, spoken, next_actions = await service.improve_bullet(req.bullet)
        elif req.action == "daily_question":
            data, spoken, next_actions = await service.get_daily_question(
                user_id=principal.user_id,
            )
        elif req.action == "check_answer":
            if not req.question_key:
                raise InvalidInputError("question_key is required to check an answer.")
            if not req.answer:
                raise InvalidInputError("Please provide an answer to check.")
            data, spoken, next_actions = await service.check_daily_answer(
                user_id=principal.user_id,
                question_key=req.question_key,
                answer=req.answer,
            )
        else:
            raise InvalidInputError(
                f"Unknown action '{req.action}'. Expected improve_bullet, daily_question, "
                "or check_answer."
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
        logger.exception("Unexpected error in career_practice tool: %s", exc)
        return fail(SahayakError(), module="career", version="0.1.0")
