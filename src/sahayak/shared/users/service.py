"""Domain service for platform user provisioning and lifecycle management."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from sahayak.core.db.session import UnitOfWork
from sahayak.shared.users.models import User, UserIdentity
from sahayak.shared.users.repo import UserRepository

if TYPE_CHECKING:
    from sahayak.core.db.session import SessionFactory


class UserService:
    """Coordinates user provisioning and identity resolution."""

    def __init__(
        self,
        session_factory: SessionFactory,
        repo: UserRepository | None = None,
    ) -> None:
        """Store the injected session factory and repository."""
        self._session_factory = session_factory
        self._repo = repo or UserRepository()

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        """Fetch an active user by their internal UUID."""
        async with UnitOfWork(self._session_factory) as uow:
            return await self._repo.get_by_id(uow.session, user_id)

    async def get_or_create_by_identity(
        self,
        issuer: str,
        subject: str,
        locale: str = "en-US",
        timezone: str = "UTC",
    ) -> User:
        """Fetch an existing user or provision a new one idempotently.

        Handles concurrent first-requests by catching unique constraint
        violations on the (issuer, subject) pair and falling back to the
        committed user row.
        """
        async with UnitOfWork(self._session_factory) as uow:
            existing = await self._repo.get_by_identity(uow.session, issuer, subject)
            if existing is not None:
                return existing

            try:
                async with uow.session.begin_nested():
                    return await self._repo.create_user_with_identity(
                        uow.session,
                        issuer=issuer,
                        subject=subject,
                        locale=locale,
                        timezone=timezone,
                    )
            except IntegrityError:
                # Concurrent request created the identity first; fetch the winner.
                user = await self._repo.get_by_identity(uow.session, issuer, subject)
                if user is not None:
                    return user
                raise

    async def get_identities(self, user_id: uuid.UUID) -> list[UserIdentity]:
        """Fetch all external identities linked to a user."""
        async with UnitOfWork(self._session_factory) as uow:
            return await self._repo.get_identities(uow.session, user_id)

    async def soft_delete_user(self, user_id: uuid.UUID) -> bool:
        """Mark a user as deleted."""
        async with UnitOfWork(self._session_factory) as uow:
            return await self._repo.soft_delete_user(uow.session, user_id)

    async def hard_delete_user(
        self, user_id: uuid.UUID, session: AsyncSession | None = None
    ) -> bool:
        """Permanently remove a user and all cascade-dependent identities."""
        if session is not None:
            return await self._repo.hard_delete_user(session, user_id)
        async with UnitOfWork(self._session_factory) as uow:
            return await self._repo.hard_delete_user(uow.session, user_id)
