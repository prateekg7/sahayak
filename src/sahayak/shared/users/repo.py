"""Database repository for user and identity persistence."""

from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from sahayak.shared.users.models import User, UserIdentity


class UserRepository:
    """Encapsulates PostgreSQL operations for users and identities."""

    async def get_by_id(self, session: AsyncSession, user_id: uuid.UUID) -> User | None:
        """Fetch an active user by their internal UUID."""
        stmt = select(User).where(User.id == user_id, User.deleted_at.is_(None))
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_identity(
        self, session: AsyncSession, issuer: str, subject: str
    ) -> User | None:
        """Fetch an active user matching an external IdP identity."""
        stmt = (
            select(User)
            .join(UserIdentity, UserIdentity.user_id == User.id)
            .where(
                UserIdentity.issuer == issuer,
                UserIdentity.subject == subject,
                User.deleted_at.is_(None),
            )
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_user_with_identity(
        self,
        session: AsyncSession,
        issuer: str,
        subject: str,
        locale: str = "en-US",
        timezone: str = "UTC",
    ) -> User:
        """Create a new platform user and associate their first external identity."""
        user = User(locale=locale, timezone=timezone)
        session.add(user)
        await session.flush()

        identity = UserIdentity(
            user_id=user.id,
            issuer=issuer,
            subject=subject,
        )
        session.add(identity)
        await session.flush()
        return user

    async def get_identities(self, session: AsyncSession, user_id: uuid.UUID) -> list[UserIdentity]:
        """Fetch all external identities associated with a user."""
        stmt = select(UserIdentity).where(UserIdentity.user_id == user_id)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def soft_delete_user(self, session: AsyncSession, user_id: uuid.UUID) -> bool:
        """Mark a user as deleted without removing historical records."""
        stmt = (
            update(User)
            .where(User.id == user_id, User.deleted_at.is_(None))
            .values(deleted_at=func.now())
        )
        result = await session.execute(stmt)
        if isinstance(result, CursorResult):
            return result.rowcount > 0
        return False

    async def hard_delete_user(self, session: AsyncSession, user_id: uuid.UUID) -> bool:
        """Permanently delete a user row, cascading to user_identities."""
        from sqlalchemy import delete

        stmt = delete(User).where(User.id == user_id)
        result = await session.execute(stmt)
        if isinstance(result, CursorResult):
            return result.rowcount > 0
        return False
