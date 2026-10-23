"""SQLAlchemy repository adapter for health entries (T7.1)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sahayak.modules.health.models import HealthEntry
from sahayak.modules.health.ports import HealthRepositoryPort


class SQLAlchemyHealthRepository(HealthRepositoryPort):
    """SQLAlchemy implementation of HealthRepositoryPort."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_entry(
        self,
        user_id: uuid.UUID,
        kind: str,
        data: dict[str, Any],
        occurred_at: datetime | None = None,
    ) -> HealthEntry:
        """Create and persist a new health entry."""
        entry = HealthEntry(
            user_id=user_id,
            kind=kind.lower().strip(),
            data=data,
            occurred_at=occurred_at or datetime.now(),
            is_deleted=False,
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def get_entry(
        self,
        user_id: uuid.UUID,
        entry_id: uuid.UUID,
    ) -> HealthEntry | None:
        """Retrieve an entry by ID, scoped by user_id."""
        stmt = select(HealthEntry).where(
            HealthEntry.id == entry_id,
            HealthEntry.user_id == user_id,
            HealthEntry.is_deleted.is_(False),
        )
        res = await self.session.execute(stmt)
        return res.scalars().first()

    async def list_entries(
        self,
        user_id: uuid.UUID,
        kind: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 10,
    ) -> list[HealthEntry]:
        """List active entries for a user, ordered by occurred_at DESC."""
        stmt = select(HealthEntry).where(
            HealthEntry.user_id == user_id,
            HealthEntry.is_deleted.is_(False),
        )
        if kind:
            stmt = stmt.where(HealthEntry.kind == kind.lower().strip())
        if since:
            stmt = stmt.where(HealthEntry.occurred_at >= since)
        if until:
            stmt = stmt.where(HealthEntry.occurred_at <= until)

        stmt = stmt.order_by(HealthEntry.occurred_at.desc(), HealthEntry.created_at.desc()).limit(
            limit
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def undo_last_entry(
        self,
        user_id: uuid.UUID,
        kind: str | None = None,
    ) -> HealthEntry | None:
        """Undo the most recent active health entry by marking it deleted."""
        stmt = select(HealthEntry).where(
            HealthEntry.user_id == user_id,
            HealthEntry.is_deleted.is_(False),
        )
        if kind:
            stmt = stmt.where(HealthEntry.kind == kind.lower().strip())

        stmt = stmt.order_by(HealthEntry.occurred_at.desc(), HealthEntry.created_at.desc()).limit(1)

        res = await self.session.execute(stmt)
        latest = res.scalars().first()
        if latest is None:
            return None

        latest.is_deleted = True
        await self.session.flush()
        return latest

    async def delete_entry(
        self,
        user_id: uuid.UUID,
        entry_id: uuid.UUID,
    ) -> bool:
        """Soft delete a specific health entry."""
        entry = await self.get_entry(user_id, entry_id)
        if entry is None:
            return False

        entry.is_deleted = True
        await self.session.flush()
        return True
