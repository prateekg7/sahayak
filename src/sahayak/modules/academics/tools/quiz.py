"""Quiz MCP tools for starting and answering interactive academic quizzes."""

from __future__ import annotations

import logging
from typing import Any

from sahayak.core.auth.principal import allow_anonymous, get_current_principal
from sahayak.core.config import get_settings
from sahayak.core.envelope import fail, ok
from sahayak.core.errors import SahayakError
from sahayak.core.idempotency import idempotent
from sahayak.core.observability.instrumentation import instrument_tool
from sahayak.modules.academics.schemas import (
    QuizOption,
    QuizStartRequest,
    QuizStartResponseData,
)
from sahayak.modules.academics.service.quiz import QuizService

logger = logging.getLogger(__name__)

QUIZ_START_DESCRIPTION = (
    "Starts an interactive multiple-choice quiz on any academic topic. "
    "Use when the user asks to start a quiz or be tested, such as "
    "'Alexa, quiz me on photosynthesis'. "
    "Do not use for answering questions in an active quiz; use quiz_answer instead."
)

_quiz_service: QuizService | None = None


def set_quiz_service(service: QuizService | None) -> None:
    """Set or override the module-level quiz service instance."""
    global _quiz_service
    _quiz_service = service


def get_quiz_service() -> QuizService:
    """Return the configured quiz service instance or lazily initialize one."""
    global _quiz_service
    if _quiz_service is None:
        settings = get_settings()
        from sahayak.core.db.session import create_engine, create_session_factory

        engine = create_engine(settings)
        session_factory = create_session_factory(engine)
        _quiz_service = QuizService(
            session_factory=session_factory,
            quiz_ttl_minutes=settings.quiz_ttl_minutes,
        )
    return _quiz_service


@allow_anonymous
@idempotent(tool_name="quiz_start")
async def quiz_start(
    topic: str | None = None,
    source: str = "topic",
    difficulty: str = "medium",
    num_questions: int = 5,
    request_id: str = "",
) -> dict[str, Any]:
    """Start an interactive multiple-choice quiz on any academic topic."""
    if request_id:
        from sahayak.core.request_id import set_request_id

        set_request_id(request_id)

    async with instrument_tool("quiz_start", "academics"):
        service = get_quiz_service()
        principal = get_current_principal()

        try:
            req = QuizStartRequest(
                topic=topic,
                source=source,  # type: ignore[arg-type]
                difficulty=difficulty,  # type: ignore[arg-type]
                num_questions=num_questions,
                request_id=request_id or None,
            )

            started = await service.start_quiz(
                user_id=principal.user_id,
                topic=req.topic,
                source=req.source,
                difficulty=req.difficulty,
                num_questions=req.num_questions,
            )

            data = QuizStartResponseData(
                quiz_id=str(started.quiz_id),
                number=started.current_number,
                total=started.total_questions,
                topic=started.topic_display_name,
                difficulty=started.difficulty.value,
                question=started.stem,
                options=[QuizOption(key=k, text=v) for k, v in sorted(started.options.items())],
            ).model_dump()

            return ok(
                spoken_summary=started.spoken_summary,
                data=data,
                next_actions=["Answer with an option letter or text, like 'Option A'."],
                module="academics",
                version="0.1.0",
            )
        except SahayakError as err:
            return fail(err, module="academics", version="0.1.0")
        except Exception as exc:
            logger.exception("Unexpected error in quiz_start: %s", exc)
            return fail(SahayakError(), module="academics", version="0.1.0")
