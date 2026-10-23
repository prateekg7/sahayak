"""SQLAlchemy repository adapter for pantry items and preferences (T9.3)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sahayak.modules.home.models import HouseholdPreference, PantryItem
from sahayak.modules.home.ports import PantryRepositoryPort


class SQLAlchemyPantryRepository(PantryRepositoryPort):
    """PostgreSQL adapter for pantry inventory and household diet preferences."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_or_update_item(
        self,
        *,
        household_id: uuid.UUID,
        item_name: str,
        quantity: str | None = None,
        expires_at: date | None = None,
        added_by: uuid.UUID | None = None,
    ) -> PantryItem:
        stmt = select(PantryItem).where(
            PantryItem.household_id == household_id,
            func.lower(PantryItem.item_name) == func.lower(item_name),
        )
        res = await self._session.execute(stmt)
        existing = res.scalar_one_or_none()

        now = datetime.now(UTC)
        if existing:
            if quantity:
                existing.quantity = quantity
            if expires_at is not None:
                existing.expires_at = expires_at
            existing.added_by = added_by
            existing.updated_at = now
            await self._session.flush()
            return existing

        item = PantryItem(
            id=uuid.uuid4(),
            household_id=household_id,
            item_name=item_name,
            quantity=quantity,
            expires_at=expires_at,
            added_by=added_by,
            created_at=now,
            updated_at=now,
        )
        self._session.add(item)
        await self._session.flush()
        return item

    async def list_items(
        self,
        *,
        household_id: uuid.UUID,
    ) -> list[PantryItem]:
        stmt = (
            select(PantryItem)
            .where(PantryItem.household_id == household_id)
            .order_by(PantryItem.expires_at.asc().nulls_last(), PantryItem.created_at.asc())
        )
        res = await self._session.execute(stmt)
        return list(res.scalars().all())

    async def find_item_by_name(
        self,
        *,
        household_id: uuid.UUID,
        item_name: str,
    ) -> PantryItem | None:
        stmt = select(PantryItem).where(
            PantryItem.household_id == household_id,
            func.lower(PantryItem.item_name) == func.lower(item_name),
        )
        res = await self._session.execute(stmt)
        return res.scalars().first()

    async def remove_item(
        self,
        *,
        item_id: uuid.UUID,
    ) -> bool:
        stmt = delete(PantryItem).where(PantryItem.id == item_id).returning(PantryItem.id)
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none() is not None

    async def get_or_create_preferences(
        self,
        *,
        household_id: uuid.UUID,
    ) -> HouseholdPreference:
        stmt = select(HouseholdPreference).where(HouseholdPreference.household_id == household_id)
        res = await self._session.execute(stmt)
        existing = res.scalar_one_or_none()
        if existing:
            return existing

        now = datetime.now(UTC)
        pref = HouseholdPreference(
            household_id=household_id,
            diet="any",
            allergies=[],
            created_at=now,
            updated_at=now,
        )
        self._session.add(pref)
        await self._session.flush()
        return pref

    async def update_preferences(
        self,
        *,
        household_id: uuid.UUID,
        diet: str,
        allergies: list[str],
    ) -> HouseholdPreference:
        pref = await self.get_or_create_preferences(household_id=household_id)
        pref.diet = diet
        pref.allergies = allergies
        pref.updated_at = datetime.now(UTC)
        await self._session.flush()
        return pref
