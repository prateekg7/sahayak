"""SQLAlchemy repository adapter for job applications (T8.2)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from sahayak.modules.career.models import Application
from sahayak.modules.career.ports import ApplicationRepositoryPort


class SQLAlchemyApplicationRepository(ApplicationRepositoryPort):
    """PostgreSQL adapter for job application tracking."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_application(
        self,
        *,
        user_id: uuid.UUID,
        company: str,
        role: str,
        status: str = "applied",
        follow_up_at: datetime | None = None,
        notes: str | None = None,
    ) -> Application:
        app = Application(
            user_id=user_id,
            company=company,
            role=role,
            status=status,
            follow_up_at=follow_up_at,
            notes=notes,
        )
        self._session.add(app)
        await self._session.flush()
        return app

    async def update_status(
        self,
        *,
        user_id: uuid.UUID,
        application_id: uuid.UUID,
        status: str,
        notes: str | None = None,
    ) -> Application | None:
        stmt = select(Application).where(
            Application.id == application_id,
            Application.user_id == user_id,
        )
        res = await self._session.execute(stmt)
        app = res.scalar_one_or_none()
        if not app:
            return None

        app.status = status
        if notes:
            app.notes = notes
        await self._session.flush()
        return app

    async def get_application(
        self,
        *,
        user_id: uuid.UUID,
        application_id: uuid.UUID,
    ) -> Application | None:
        stmt = select(Application).where(
            Application.id == application_id,
            Application.user_id == user_id,
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_applications(
        self,
        *,
        user_id: uuid.UUID,
        status: str | None = None,
        limit: int = 10,
    ) -> list[Application]:
        stmt = select(Application).where(Application.user_id == user_id)
        if status:
            stmt = stmt.where(Application.status == status)

        stmt = stmt.order_by(Application.created_at.desc(), Application.id.desc()).limit(limit)
        res = await self._session.execute(stmt)
        return list(res.scalars().all())

    async def list_due_followups(
        self,
        *,
        user_id: uuid.UUID,
        before_time: datetime | None = None,
        limit: int = 10,
    ) -> list[Application]:
        stmt = select(Application).where(
            Application.user_id == user_id,
            Application.follow_up_at.is_not(None),
            Application.status.not_in(["rejected", "withdrawn"]),
        )
        if before_time:
            stmt = stmt.where(Application.follow_up_at <= before_time)

        stmt = stmt.order_by(Application.follow_up_at.asc(), Application.id.asc()).limit(limit)
        res = await self._session.execute(stmt)
        return list(res.scalars().all())

    async def delete_application(
        self,
        *,
        user_id: uuid.UUID,
        application_id: uuid.UUID,
    ) -> bool:
        stmt = (
            delete(Application)
            .where(
                Application.id == application_id,
                Application.user_id == user_id,
            )
            .execution_options(synchronize_session=False)
        )
        res = await self._session.execute(stmt)
        return bool(int(getattr(res, "rowcount", 0) or 0) > 0)
