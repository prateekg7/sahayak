"""SQLAlchemy adapter for language practice sessions (T11.2)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from sahayak.modules.language.models import PracticeSession
from sahayak.modules.language.ports import PracticeSessionRepositoryPort


class SQLAlchemyPracticeSessionRepository(PracticeSessionRepositoryPort):
    """SQLAlchemy implementation of PracticeSessionRepositoryPort."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_session_by_id(
        self,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> PracticeSession | None:
        stmt = select(PracticeSession).where(
            PracticeSession.id == session_id,
            PracticeSession.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_session(
        self,
        user_id: uuid.UUID,
        language: str | None = None,
    ) -> PracticeSession | None:
        stmt = select(PracticeSession).where(
            PracticeSession.user_id == user_id,
            PracticeSession.status == "active",
        )
        if language:
            stmt = stmt.where(PracticeSession.language == language.lower())
        stmt = stmt.order_by(PracticeSession.created_at.desc())
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def create_session(self, session: PracticeSession) -> PracticeSession:
        self._session.add(session)
        await self._session.flush()
        return session

    async def save_session(self, session: PracticeSession) -> PracticeSession:
        self._session.add(session)
        await self._session.flush()
        return session

    async def delete_all_for_user(self, user_id: uuid.UUID) -> int:
        stmt = delete(PracticeSession).where(PracticeSession.user_id == user_id)
        result = await self._session.execute(stmt)
        rowcount = getattr(result, "rowcount", 0)
        return int(rowcount) if isinstance(rowcount, int) else 0

    async def export_for_user(self, user_id: uuid.UUID) -> list[dict[str, Any]]:
        stmt = (
            select(PracticeSession)
            .where(PracticeSession.user_id == user_id)
            .order_by(PracticeSession.created_at.asc())
        )
        result = await self._session.execute(stmt)
        return [s.to_dict() for s in result.scalars().all()]
