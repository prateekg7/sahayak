"""SQLAlchemy implementation of FocusSessionRepositoryPort (T5.4)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sahayak.modules.productivity.models import FocusSession


class SQLAlchemyFocusRepository:
    """Repository managing focus session persistence and statistics."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_session(
        self,
        user_id: uuid.UUID,
        duration_minutes: int,
        started_at: datetime,
        planned_end_at: datetime,
        task_label: str | None = None,
    ) -> FocusSession:
        """Create and persist a new focus session."""
        session = FocusSession(
            user_id=user_id,
            task_label=task_label.strip() if task_label else None,
            duration_minutes=duration_minutes,
            started_at=started_at,
            planned_end_at=planned_end_at,
            status="active",
        )
        self.session.add(session)
        await self.session.flush()
        return session

    async def get_active_session(self, user_id: uuid.UUID) -> FocusSession | None:
        """Get the most recent active session for a user."""
        stmt = (
            select(FocusSession)
            .where(FocusSession.user_id == user_id, FocusSession.status == "active")
            .order_by(desc(FocusSession.started_at))
            .limit(1)
        )
        res = await self.session.execute(stmt)
        return res.scalars().first()

    async def update_session_status(
        self,
        session_id: uuid.UUID,
        status: str,
        actual_end_at: datetime | None = None,
    ) -> FocusSession | None:
        """Update session status and optional completion timestamp."""
        stmt = select(FocusSession).where(FocusSession.id == session_id)
        res = await self.session.execute(stmt)
        record = res.scalars().first()
        if record is None:
            return None

        record.status = status
        if actual_end_at is not None:
            record.actual_end_at = actual_end_at
        await self.session.flush()
        return record

    async def list_sessions(
        self,
        user_id: uuid.UUID,
        limit: int = 10,
    ) -> list[FocusSession]:
        """List recent focus sessions for a user."""
        stmt = (
            select(FocusSession)
            .where(FocusSession.user_id == user_id)
            .order_by(desc(FocusSession.started_at))
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def get_session_stats(
        self,
        user_id: uuid.UUID,
        since_today: datetime,
    ) -> tuple[int, int, int]:
        """Get (total_completed, total_minutes_focused, today_completed)."""
        # Total completed
        total_stmt = select(
            func.count(FocusSession.id),
            func.coalesce(func.sum(FocusSession.duration_minutes), 0),
        ).where(FocusSession.user_id == user_id, FocusSession.status == "completed")
        total_res = await self.session.execute(total_stmt)
        row = total_res.first()
        total_completed = int(row[0]) if row and row[0] is not None else 0
        total_minutes = int(row[1]) if row and row[1] is not None else 0

        # Today completed
        today_stmt = select(func.count(FocusSession.id)).where(
            FocusSession.user_id == user_id,
            FocusSession.status == "completed",
            FocusSession.started_at >= since_today,
        )
        today_res = await self.session.execute(today_stmt)
        today_val = today_res.scalar()
        today_completed = int(today_val) if today_val is not None else 0

        return total_completed, total_minutes, today_completed
