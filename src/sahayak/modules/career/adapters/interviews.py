"""SQLAlchemy repository adapter for career module (T8.1)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from sahayak.modules.career.domain.rubric import RubricScore
from sahayak.modules.career.models import InterviewSession, InterviewTurn
from sahayak.modules.career.ports import InterviewRepositoryPort


class SQLAlchemyInterviewRepository(InterviewRepositoryPort):
    """PostgreSQL adapter for mock interview sessions and turns."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_session(
        self,
        *,
        user_id: uuid.UUID,
        role: str,
        level: str,
        total_questions: int,
        questions: list[dict[str, Any]],
    ) -> InterviewSession:
        session = InterviewSession(
            user_id=user_id,
            role=role,
            level=level,
            total_questions=total_questions,
            current_question_index=0,
            status="in_progress",
            questions=questions,
        )
        self._session.add(session)
        await self._session.flush()
        return session

    async def get_session(
        self,
        *,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> InterviewSession | None:
        stmt = select(InterviewSession).where(
            InterviewSession.id == session_id,
            InterviewSession.user_id == user_id,
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def update_session_progress(
        self,
        *,
        session_id: uuid.UUID,
        current_question_index: int,
        status: str,
    ) -> InterviewSession | None:
        stmt = select(InterviewSession).where(InterviewSession.id == session_id)
        res = await self._session.execute(stmt)
        sess = res.scalar_one_or_none()
        if not sess:
            return None

        sess.current_question_index = current_question_index
        sess.status = status
        if status in ("completed", "abandoned"):
            sess.finished_at = datetime.now(UTC)
        await self._session.flush()
        return sess

    async def list_sessions(
        self,
        *,
        user_id: uuid.UUID,
        limit: int = 5,
    ) -> list[InterviewSession]:
        stmt = (
            select(InterviewSession)
            .where(InterviewSession.user_id == user_id)
            .order_by(InterviewSession.created_at.desc(), InterviewSession.id.desc())
            .limit(limit)
        )
        res = await self._session.execute(stmt)
        return list(res.scalars().all())

    async def create_turn(
        self,
        *,
        session_id: uuid.UUID,
        question_index: int,
        question_text: str,
        user_answer: str,
        score: RubricScore,
    ) -> InterviewTurn:
        turn = InterviewTurn(
            session_id=session_id,
            question_index=question_index,
            question_text=question_text,
            user_answer=user_answer,
            clarity_score=score.clarity_score,
            relevance_score=score.relevance_score,
            depth_score=score.depth_score,
            feedback_tips=score.feedback_tips,
            feedback_spoken=score.feedback_spoken,
            prompt_version=score.prompt_version,
        )
        self._session.add(turn)
        await self._session.flush()
        return turn

    async def get_turns(
        self,
        *,
        session_id: uuid.UUID,
    ) -> list[InterviewTurn]:
        stmt = (
            select(InterviewTurn)
            .where(InterviewTurn.session_id == session_id)
            .order_by(InterviewTurn.question_index.asc())
        )
        res = await self._session.execute(stmt)
        return list(res.scalars().all())

    async def delete_user_data(self, user_id: uuid.UUID) -> int:
        """Privacy hook: deletes all interview sessions for user (cascades to turns)."""
        stmt = (
            delete(InterviewSession)
            .where(InterviewSession.user_id == user_id)
            .execution_options(synchronize_session=False)
        )
        res = await self._session.execute(stmt)
        return int(getattr(res, "rowcount", 0) or 0)

    async def export_user_data(self, user_id: uuid.UUID) -> dict[str, Any]:
        """Privacy hook: exports all interview sessions and turns for user."""
        sessions = await self.list_sessions(user_id=user_id, limit=100)
        out = []
        for s in sessions:
            turns = await self.get_turns(session_id=s.id)
            s_dict = s.to_dict()
            s_dict["turns"] = [t.to_dict() for t in turns]
            out.append(s_dict)
        return {"interview_sessions": out}
