"""Ports for career module (T8.1)."""

from __future__ import annotations

import uuid
from typing import Any, Protocol

from sahayak.modules.career.domain.rubric import RubricScore
from sahayak.modules.career.models import InterviewSession, InterviewTurn


class InterviewRepositoryPort(Protocol):
    """Port for persisting career mock interview sessions and evaluated turns."""

    async def create_session(
        self,
        *,
        user_id: uuid.UUID,
        role: str,
        level: str,
        total_questions: int,
        questions: list[dict[str, Any]],
    ) -> InterviewSession: ...

    async def get_session(
        self,
        *,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> InterviewSession | None: ...

    async def update_session_progress(
        self,
        *,
        session_id: uuid.UUID,
        current_question_index: int,
        status: str,
    ) -> InterviewSession | None: ...

    async def list_sessions(
        self,
        *,
        user_id: uuid.UUID,
        limit: int = 5,
    ) -> list[InterviewSession]: ...

    async def create_turn(
        self,
        *,
        session_id: uuid.UUID,
        question_index: int,
        question_text: str,
        user_answer: str,
        score: RubricScore,
    ) -> InterviewTurn: ...

    async def get_turns(
        self,
        *,
        session_id: uuid.UUID,
    ) -> list[InterviewTurn]: ...

    async def delete_user_data(self, user_id: uuid.UUID) -> int: ...

    async def export_user_data(self, user_id: uuid.UUID) -> dict[str, Any]: ...


class InterviewEvaluationPort(Protocol):
    """Port for evaluating interview answers using structured LLM rubric."""

    async def evaluate(
        self,
        *,
        role: str,
        level: str,
        question: str,
        answer: str,
    ) -> RubricScore: ...


class ApplicationRepositoryPort(Protocol):
    """Port for persisting job applications and follow-up deadlines (T8.2)."""

    async def create_application(
        self,
        *,
        user_id: uuid.UUID,
        company: str,
        role: str,
        status: str = "applied",
        follow_up_at: Any | None = None,
        notes: str | None = None,
    ) -> Any: ...

    async def update_status(
        self,
        *,
        user_id: uuid.UUID,
        application_id: uuid.UUID,
        status: str,
        notes: str | None = None,
    ) -> Any | None: ...

    async def get_application(
        self,
        *,
        user_id: uuid.UUID,
        application_id: uuid.UUID,
    ) -> Any | None: ...

    async def list_applications(
        self,
        *,
        user_id: uuid.UUID,
        status: str | None = None,
        limit: int = 10,
    ) -> list[Any]: ...

    async def list_due_followups(
        self,
        *,
        user_id: uuid.UUID,
        before_time: Any | None = None,
        limit: int = 10,
    ) -> list[Any]: ...

    async def delete_application(
        self,
        *,
        user_id: uuid.UUID,
        application_id: uuid.UUID,
    ) -> bool: ...


class PracticeRepositoryPort(Protocol):
    """Port for recording daily career practice question answers (T8.3)."""

    async def record_daily_practice(
        self,
        *,
        user_id: uuid.UUID,
        question_key: str,
        question_text: str,
        user_answer: str,
        is_correct: bool,
        feedback: str,
    ) -> Any: ...

    async def get_answered_keys(
        self,
        *,
        user_id: uuid.UUID,
    ) -> set[str]: ...

    async def get_practice_stats(
        self,
        *,
        user_id: uuid.UUID,
    ) -> dict[str, Any]: ...
