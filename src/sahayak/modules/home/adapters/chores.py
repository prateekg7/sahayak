"""SQLAlchemy repository adapter for household chores (T9.3)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from sahayak.modules.home.models import Chore
from sahayak.modules.home.ports import ChoreRepositoryPort


class SQLAlchemyChoreRepository(ChoreRepositoryPort):
    """PostgreSQL adapter for chore entities."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_chore(
        self,
        *,
        household_id: uuid.UUID,
        title: str,
        frequency: str = "weekly",
        rotation_members: list[str] | None = None,
        assigned_to: uuid.UUID | None = None,
        next_due_at: datetime | None = None,
    ) -> Chore:
        now = datetime.now(UTC)
        chore = Chore(
            id=uuid.uuid4(),
            household_id=household_id,
            title=title,
            frequency=frequency,
            rotation_members=rotation_members or [],
            rotation_index=0,
            assigned_to=assigned_to,
            next_due_at=next_due_at,
            created_at=now,
            updated_at=now,
        )
        self._session.add(chore)
        await self._session.flush()
        return chore

    async def get_chore(
        self,
        *,
        household_id: uuid.UUID,
        chore_id: uuid.UUID,
    ) -> Chore | None:
        stmt = select(Chore).where(
            Chore.id == chore_id,
            Chore.household_id == household_id,
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def find_chore_by_title(
        self,
        *,
        household_id: uuid.UUID,
        title: str,
    ) -> Chore | None:
        stmt = select(Chore).where(
            Chore.household_id == household_id,
            func.lower(Chore.title) == func.lower(title),
        )
        res = await self._session.execute(stmt)
        return res.scalars().first()

    async def list_chores(
        self,
        *,
        household_id: uuid.UUID,
    ) -> list[Chore]:
        stmt = (
            select(Chore)
            .where(Chore.household_id == household_id)
            .order_by(Chore.next_due_at.asc().nulls_last(), Chore.created_at.asc())
        )
        res = await self._session.execute(stmt)
        return list(res.scalars().all())

    async def complete_chore(
        self,
        *,
        chore_id: uuid.UUID,
        completed_by: uuid.UUID | None,
        completed_at: datetime,
        next_assigned_to: uuid.UUID | None,
        next_rotation_index: int,
        next_due_at: datetime | None,
    ) -> Chore | None:
        now = datetime.now(UTC)
        stmt = (
            update(Chore)
            .where(Chore.id == chore_id)
            .values(
                last_completed_at=completed_at,
                last_completed_by=completed_by,
                assigned_to=next_assigned_to,
                rotation_index=next_rotation_index,
                next_due_at=next_due_at,
                updated_at=now,
            )
            .returning(Chore)
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def update_assignment(
        self,
        *,
        chore_id: uuid.UUID,
        assigned_to: uuid.UUID | None,
        rotation_members: list[str] | None = None,
    ) -> Chore | None:
        now = datetime.now(UTC)
        values: dict[str, Any] = {"assigned_to": assigned_to, "updated_at": now}
        if rotation_members is not None:
            values["rotation_members"] = rotation_members

        stmt = update(Chore).where(Chore.id == chore_id).values(**values).returning(Chore)
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def delete_chore(
        self,
        *,
        chore_id: uuid.UUID,
    ) -> bool:
        stmt = delete(Chore).where(Chore.id == chore_id).returning(Chore.id)
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none() is not None
