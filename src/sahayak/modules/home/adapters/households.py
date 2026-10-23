"""SQLAlchemy repository adapter for households, memberships, and invites (T9.1)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from sahayak.modules.home.models import Household, HouseholdInvite, HouseholdMembership
from sahayak.modules.home.ports import HouseholdRepositoryPort


class SQLAlchemyHouseholdRepository(HouseholdRepositoryPort):
    """PostgreSQL adapter for home tenancy operations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_household(
        self,
        *,
        created_by: uuid.UUID,
        name: str,
    ) -> tuple[Household, HouseholdMembership]:
        household = Household(
            id=uuid.uuid4(),
            name=name,
            created_by=created_by,
        )
        self._session.add(household)
        await self._session.flush()

        membership = HouseholdMembership(
            id=uuid.uuid4(),
            household_id=household.id,
            user_id=created_by,
            role="owner",
        )
        self._session.add(membership)
        await self._session.flush()

        return household, membership

    async def get_household(
        self,
        *,
        household_id: uuid.UUID,
    ) -> Household | None:
        stmt = select(Household).where(Household.id == household_id)
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_membership(
        self,
        *,
        household_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> HouseholdMembership | None:
        stmt = select(HouseholdMembership).where(
            HouseholdMembership.household_id == household_id,
            HouseholdMembership.user_id == user_id,
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_user_households(
        self,
        *,
        user_id: uuid.UUID,
    ) -> list[tuple[Household, HouseholdMembership]]:
        stmt = (
            select(Household, HouseholdMembership)
            .join(HouseholdMembership, Household.id == HouseholdMembership.household_id)
            .where(HouseholdMembership.user_id == user_id)
            .order_by(HouseholdMembership.joined_at.desc())
        )
        res = await self._session.execute(stmt)
        return [(row[0], row[1]) for row in res.all()]

    async def create_invite(
        self,
        *,
        household_id: uuid.UUID,
        created_by: uuid.UUID,
        code: str,
        expires_at: datetime,
    ) -> HouseholdInvite:
        invite = HouseholdInvite(
            id=uuid.uuid4(),
            household_id=household_id,
            code=code,
            created_by=created_by,
            expires_at=expires_at,
        )
        self._session.add(invite)
        await self._session.flush()
        return invite

    async def get_active_invite(
        self,
        *,
        code: str,
        now: datetime,
    ) -> HouseholdInvite | None:
        stmt = select(HouseholdInvite).where(
            HouseholdInvite.code == code,
            HouseholdInvite.used_at.is_(None),
            HouseholdInvite.expires_at > now,
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def mark_invite_used(
        self,
        *,
        invite_id: uuid.UUID,
        used_by: uuid.UUID,
        now: datetime,
    ) -> None:
        stmt = (
            update(HouseholdInvite)
            .where(HouseholdInvite.id == invite_id)
            .values(used_at=now, used_by=used_by)
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def add_member(
        self,
        *,
        household_id: uuid.UUID,
        user_id: uuid.UUID,
        role: str = "member",
    ) -> HouseholdMembership:
        membership = HouseholdMembership(
            id=uuid.uuid4(),
            household_id=household_id,
            user_id=user_id,
            role=role,
        )
        self._session.add(membership)
        await self._session.flush()
        return membership

    async def list_members(
        self,
        *,
        household_id: uuid.UUID,
    ) -> list[HouseholdMembership]:
        stmt = (
            select(HouseholdMembership)
            .where(HouseholdMembership.household_id == household_id)
            .order_by(HouseholdMembership.joined_at.asc())
        )
        res = await self._session.execute(stmt)
        return list(res.scalars().all())

    async def remove_member(
        self,
        *,
        household_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        stmt = (
            delete(HouseholdMembership)
            .where(
                HouseholdMembership.household_id == household_id,
                HouseholdMembership.user_id == user_id,
            )
            .returning(HouseholdMembership.id)
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none() is not None

    async def delete_household(
        self,
        *,
        household_id: uuid.UUID,
    ) -> bool:
        stmt = delete(Household).where(Household.id == household_id).returning(Household.id)
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none() is not None
