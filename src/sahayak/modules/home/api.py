"""Public cross-module API for the home and family module (T9.1)."""

from __future__ import annotations

import uuid
from typing import Any

from sahayak.core.db.session import UnitOfWork
from sahayak.core.errors import ForbiddenError
from sahayak.modules.home.adapters.households import SQLAlchemyHouseholdRepository
from sahayak.modules.home.models import Household, HouseholdMembership


class HomeAPI:
    """Published interface for other modules to verify household tenancy and memberships."""

    def __init__(self, session_factory: Any) -> None:
        self.session_factory = session_factory

    async def assert_member(
        self,
        *,
        household_id: uuid.UUID,
        user_id: uuid.UUID,
        required_role: str | None = None,
    ) -> HouseholdMembership:
        """Verify user is an active member of household with optional role check."""
        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyHouseholdRepository(uow.session)
            membership = await repo.get_membership(
                household_id=household_id,
                user_id=user_id,
            )

        if not membership:
            raise ForbiddenError(
                spoken="You do not have access to this household.",
                detail=f"User {user_id} is not a member of household {household_id}",
            )

        if required_role and membership.role != required_role:
            raise ForbiddenError(
                spoken=f"This action requires household {required_role} permissions.",
                detail=(f"User {user_id} has role '{membership.role}', expected '{required_role}'"),
            )

        return membership

    async def get_user_households(
        self,
        *,
        user_id: uuid.UUID,
    ) -> list[tuple[Household, HouseholdMembership]]:
        """Fetch all households for a user."""
        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyHouseholdRepository(uow.session)
            return await repo.list_user_households(user_id=user_id)

    async def get_household(
        self,
        *,
        household_id: uuid.UUID,
    ) -> Household | None:
        """Fetch household by ID."""
        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyHouseholdRepository(uow.session)
            return await repo.get_household(household_id=household_id)

    async def get_household_members(
        self,
        *,
        household_id: uuid.UUID,
    ) -> list[HouseholdMembership]:
        """Fetch all members of a household."""
        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyHouseholdRepository(uow.session)
            return await repo.list_members(household_id=household_id)
