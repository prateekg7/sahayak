"""HouseholdService orchestrating tenancy, memberships, and invite flows (T9.1)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sahayak.core.db.session import UnitOfWork
from sahayak.core.errors import ForbiddenError, NotFoundError
from sahayak.modules.home.adapters.households import SQLAlchemyHouseholdRepository
from sahayak.modules.home.domain.households import (
    format_household_created_spoken,
    format_joined_spoken,
    format_members_spoken,
    generate_invite_code,
    normalize_household_name,
    normalize_invite_code,
    sanitize_spoken_text,
)
from sahayak.modules.home.models import HouseholdMembership


class HouseholdService:
    """Service handling household creation, membership authorization, and invite onboarding."""

    def __init__(
        self,
        session_factory: Any,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.session_factory = session_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    async def assert_member(
        self,
        *,
        household_id: uuid.UUID,
        user_id: uuid.UUID,
        required_role: str | None = None,
    ) -> HouseholdMembership:
        """Verify user is an active member of household with optional role requirement."""
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

    async def create_household(
        self,
        *,
        user_id: uuid.UUID,
        name: str,
    ) -> tuple[dict[str, Any], str, list[str]]:
        """Create a new household, assign user as owner, and generate an initial invite code."""
        clean_name = normalize_household_name(name)
        now = self._clock()
        invite_code = generate_invite_code()
        expires_at = now + timedelta(hours=48)

        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyHouseholdRepository(uow.session)
            household, membership = await repo.create_household(
                created_by=user_id,
                name=clean_name,
            )
            invite = await repo.create_invite(
                household_id=household.id,
                created_by=user_id,
                code=invite_code,
                expires_at=expires_at,
            )
            await uow.session.commit()

        spoken = format_household_created_spoken(clean_name, invite_code)
        data = {
            "household": household.to_dict(),
            "membership": membership.to_dict(),
            "invite": invite.to_dict(),
        }
        next_actions = [
            f"shared_list(household_id='{household.id}', action='read')",
            f"household(action='invite', household_id='{household.id}')",
        ]
        return data, spoken, next_actions

    async def join_household(
        self,
        *,
        user_id: uuid.UUID,
        invite_code: str,
    ) -> tuple[dict[str, Any], str, list[str]]:
        """Join a household using an active invite code."""
        code = normalize_invite_code(invite_code)
        now = self._clock()

        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyHouseholdRepository(uow.session)
            invite = await repo.get_active_invite(code=code, now=now)
            if not invite:
                raise NotFoundError(
                    spoken="That invite code is invalid or has expired.",
                    detail=f"Invite code '{code}' not found or expired at {now.isoformat()}",
                )

            # Check if user is already a member
            existing = await repo.get_membership(
                household_id=invite.household_id,
                user_id=user_id,
            )
            if existing:
                household = await repo.get_household(household_id=invite.household_id)
                h_name = household.name if household else "the household"
                spoken = sanitize_spoken_text(f"You are already a member of {h_name}.")
                data = {
                    "household_id": str(invite.household_id),
                    "already_member": True,
                }
                return data, spoken, []

            household = await repo.get_household(household_id=invite.household_id)
            if not household:
                raise NotFoundError("The associated household no longer exists.")

            membership = await repo.add_member(
                household_id=household.id,
                user_id=user_id,
                role="member",
            )
            await repo.mark_invite_used(
                invite_id=invite.id,
                used_by=user_id,
                now=now,
            )
            await uow.session.commit()

        spoken = format_joined_spoken(household.name)
        data = {
            "household": household.to_dict(),
            "membership": membership.to_dict(),
        }
        next_actions = [
            f"shared_list(household_id='{household.id}', action='read')",
            f"chores(household_id='{household.id}', action='whose_turn')",
        ]
        return data, spoken, next_actions

    async def create_invite(
        self,
        *,
        user_id: uuid.UUID,
        household_id: uuid.UUID,
    ) -> tuple[dict[str, Any], str, list[str]]:
        """Generate a new 48-hour invite code for a household."""
        await self.assert_member(household_id=household_id, user_id=user_id)
        now = self._clock()
        invite_code = generate_invite_code()
        expires_at = now + timedelta(hours=48)

        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyHouseholdRepository(uow.session)
            await repo.create_invite(
                household_id=household_id,
                created_by=user_id,
                code=invite_code,
                expires_at=expires_at,
            )
            household = await repo.get_household(household_id=household_id)
            await uow.session.commit()

        h_name = household.name if household else "your household"
        spaced_code = " ".join(list(invite_code))
        spoken = sanitize_spoken_text(
            f"Here is a new invite code for {h_name}: {spaced_code}. It is valid for 48 hours."
        )
        data = {
            "household_id": str(household_id),
            "invite_code": invite_code,
            "expires_at": expires_at.isoformat(),
        }
        return data, spoken, []

    async def list_households(
        self,
        *,
        user_id: uuid.UUID,
    ) -> tuple[dict[str, Any], str, list[str]]:
        """List all households for the user."""
        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyHouseholdRepository(uow.session)
            results = await repo.list_user_households(user_id=user_id)

        items = [
            {
                "household": h.to_dict(),
                "role": m.role,
                "joined_at": m.joined_at.isoformat() if m.joined_at else None,
            }
            for h, m in results
        ]
        count = len(items)
        suffix = "s" if count != 1 else ""
        spoken = sanitize_spoken_text(
            f"You belong to {count} household{suffix}."
            if count > 0
            else "You do not belong to any household yet. Say create household to get started."
        )
        data = {"count": count, "households": items}
        return data, spoken, []

    async def list_members(
        self,
        *,
        user_id: uuid.UUID,
        household_id: uuid.UUID,
    ) -> tuple[dict[str, Any], str, list[str]]:
        """List all members of a household."""
        await self.assert_member(household_id=household_id, user_id=user_id)
        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyHouseholdRepository(uow.session)
            household = await repo.get_household(household_id=household_id)
            members = await repo.list_members(household_id=household_id)

        h_name = household.name if household else "Household"
        spoken = format_members_spoken(h_name, len(members))
        data = {
            "household_id": str(household_id),
            "count": len(members),
            "members": [m.to_dict() for m in members],
        }
        return data, spoken, []

    async def leave_household(
        self,
        *,
        user_id: uuid.UUID,
        household_id: uuid.UUID,
    ) -> tuple[dict[str, Any], str, list[str]]:
        """Leave a household."""
        membership = await self.assert_member(household_id=household_id, user_id=user_id)
        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyHouseholdRepository(uow.session)
            household = await repo.get_household(household_id=household_id)
            h_name = household.name if household else "the household"

            members = await repo.list_members(household_id=household_id)
            if len(members) <= 1:
                # Sole member, delete household
                await repo.delete_household(household_id=household_id)
            else:
                if membership.role == "owner":
                    # Transfer ownership to next member
                    next_member = next((m for m in members if m.user_id != user_id), None)
                    if next_member:
                        next_member.role = "owner"
                await repo.remove_member(household_id=household_id, user_id=user_id)
            await uow.session.commit()

        spoken = sanitize_spoken_text(f"You have left {h_name}.")
        data = {"household_id": str(household_id), "left": True}
        return data, spoken, []
