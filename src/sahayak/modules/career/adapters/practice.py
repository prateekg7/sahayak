"""SQLAlchemy repository adapter for daily career practice (T8.3)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sahayak.modules.career.models import DailyPractice
from sahayak.modules.career.ports import PracticeRepositoryPort


class SQLAlchemyPracticeRepository(PracticeRepositoryPort):
    """PostgreSQL adapter for daily career practice records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record_daily_practice(
        self,
        *,
        user_id: uuid.UUID,
        question_key: str,
        question_text: str,
        user_answer: str,
        is_correct: bool,
        feedback: str,
    ) -> DailyPractice:
        record = DailyPractice(
            user_id=user_id,
            question_key=question_key,
            question_text=question_text,
            user_answer=user_answer,
            is_correct=is_correct,
            feedback=feedback,
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def get_answered_keys(
        self,
        *,
        user_id: uuid.UUID,
    ) -> set[str]:
        stmt = select(DailyPractice.question_key).where(DailyPractice.user_id == user_id)
        res = await self._session.execute(stmt)
        return set(res.scalars().all())

    async def get_practice_stats(
        self,
        *,
        user_id: uuid.UUID,
    ) -> dict[str, Any]:
        stmt = select(
            func.count(DailyPractice.id),
            func.coalesce(
                func.sum(case((DailyPractice.is_correct.is_(True), 1), else_=0)),
                0,
            ),
        ).where(DailyPractice.user_id == user_id)
        res = await self._session.execute(stmt)
        row = res.one_or_none()
        total = int(row[0]) if row and row[0] is not None else 0
        correct = int(row[1]) if row and row[1] is not None else 0
        return {"total_attempts": total, "correct_count": correct}
