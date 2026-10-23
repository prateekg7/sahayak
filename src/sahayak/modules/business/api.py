"""Public API for cross-module interactions with the business module (T10.1)."""

from __future__ import annotations

import uuid
from typing import Any

from sahayak.core.db.session import UnitOfWork
from sahayak.core.errors import NotFoundError
from sahayak.modules.business.adapters.orders import SQLAlchemyBusinessRepository
from sahayak.modules.business.models import Business, BusinessMember


class BusinessAPI:
    """Stable public API for cross-module interaction with business tenancy."""

    def __init__(self, session_factory: Any) -> None:
        self.session_factory = session_factory

    async def assert_member(
        self,
        *,
        business_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> BusinessMember:
        """Validate that user is a member of the business or raise NotFoundError."""
        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyBusinessRepository(uow.session)
            membership = await repo.get_membership(business_id=business_id, user_id=user_id)
            if not membership:
                raise NotFoundError(
                    spoken="You do not have access to that business.",
                    detail=f"User {user_id} is not a member of {business_id}",
                )
            return membership

    async def get_user_business(self, *, user_id: uuid.UUID) -> Business | None:
        """Get the primary business for a user, if one exists."""
        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyBusinessRepository(uow.session)
            businesses = await repo.list_user_businesses(user_id=user_id)
            if not businesses:
                return None
            return businesses[0][0]
