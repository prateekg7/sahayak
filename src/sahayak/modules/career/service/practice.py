"""CareerPracticeService for resume bullet improvement and daily questions (T8.3)."""

from __future__ import annotations

import uuid
from typing import Any

from sahayak.core.db.session import UnitOfWork
from sahayak.core.errors import InvalidInputError, NotFoundError
from sahayak.modules.career.adapters.practice import SQLAlchemyPracticeRepository
from sahayak.modules.career.domain.practice import (
    CURATED_DAILY_QUESTIONS,
    evaluate_daily_answer,
    get_next_daily_question,
    improve_resume_bullet,
)
from sahayak.modules.career.domain.rubric import sanitize_spoken_text
from sahayak.shared.llm.ports import LLMClient


class CareerPracticeService:
    """Service orchestrating resume bullet improvements and daily practice questions."""

    def __init__(
        self,
        session_factory: Any,
        llm_client: LLMClient | None = None,
    ) -> None:
        self.session_factory = session_factory
        self._llm = llm_client

    async def improve_bullet(
        self,
        bullet: str,
    ) -> tuple[dict[str, Any], str, list[str]]:
        """Improve resume bullet using the Google XYZ formula."""
        if not bullet or not bullet.strip():
            raise InvalidInputError("Please provide a resume bullet point to improve.")

        result = improve_resume_bullet(bullet.strip())
        spoken = result["spoken_explanation"]
        next_actions = [
            "career_practice(action='daily_question')",
            "career_practice(action='improve_bullet')",
        ]
        return result, spoken, next_actions

    async def get_daily_question(
        self,
        *,
        user_id: uuid.UUID,
    ) -> tuple[dict[str, Any], str, list[str]]:
        """Retrieve the user's unrepeated daily career practice question."""
        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyPracticeRepository(uow.session)
            answered_keys = await repo.get_answered_keys(user_id=user_id)

        question = get_next_daily_question(answered_keys)
        spoken = sanitize_spoken_text(
            f"Here is today's career practice question on {question.topic}: "
            f"{question.stem} What is your answer?"
        )
        data = {
            "question_key": question.key,
            "topic": question.topic,
            "question_text": question.stem,
        }
        next_actions = [
            f"career_practice(action='check_answer', question_key='{question.key}', answer='...')",
            "career_practice(action='improve_bullet')",
        ]
        return data, spoken, next_actions

    async def check_daily_answer(
        self,
        *,
        user_id: uuid.UUID,
        question_key: str,
        answer: str,
    ) -> tuple[dict[str, Any], str, list[str]]:
        """Evaluate candidate answer to daily practice question and award stats."""
        if not question_key or not question_key.strip():
            raise InvalidInputError("question_key is required to check your answer.")
        if not answer or not answer.strip():
            raise InvalidInputError("Please provide an answer to check.")

        # Find question definition
        q_item = next((q for q in CURATED_DAILY_QUESTIONS if q.key == question_key.strip()), None)
        if not q_item:
            raise NotFoundError("Practice question not found. Say daily question for a new one.")

        is_correct, feedback_spoken = evaluate_daily_answer(q_item, answer.strip())

        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyPracticeRepository(uow.session)
            await repo.record_daily_practice(
                user_id=user_id,
                question_key=q_item.key,
                question_text=q_item.stem,
                user_answer=answer.strip(),
                is_correct=is_correct,
                feedback=feedback_spoken,
            )
            stats = await repo.get_practice_stats(user_id=user_id)
            await uow.session.commit()

        total = stats.get("total_attempts", 1)
        suffix = "s" if total > 1 else ""
        spoken = sanitize_spoken_text(
            f"{feedback_spoken} You completed {total} daily practice question{suffix} so far."
        )
        data = {
            "question_key": q_item.key,
            "is_correct": is_correct,
            "sample_answer": q_item.sample_answer,
            "stats": stats,
        }
        next_actions = [
            "career_practice(action='daily_question')",
            "career_practice(action='improve_bullet')",
        ]
        return data, spoken, next_actions
