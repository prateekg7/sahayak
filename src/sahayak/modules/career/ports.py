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
