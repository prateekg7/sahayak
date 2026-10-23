"""SQLAlchemy repository adapter for shared lists and items (T9.2)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from sahayak.modules.home.models import SharedList, SharedListItem
from sahayak.modules.home.ports import ListRepositoryPort


class SQLAlchemyListRepository(ListRepositoryPort):
    """PostgreSQL adapter for shared list entities."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create_list(
        self,
        *,
        household_id: uuid.UUID,
        name: str,
    ) -> SharedList:
        stmt = select(SharedList).where(
            SharedList.household_id == household_id,
            SharedList.name == name,
        )
        res = await self._session.execute(stmt)
        existing = res.scalar_one_or_none()
        if existing:
            return existing

        now = datetime.now(UTC)
        insert_stmt = (
            pg_insert(SharedList)
            .values(
                id=uuid.uuid4(),
                household_id=household_id,
                name=name,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_nothing(constraint="uq_home_lists_household_name")
            .returning(SharedList)
        )
        res_ins = await self._session.execute(insert_stmt)
        inserted = res_ins.scalar_one_or_none()
        if inserted:
            return inserted

        res_retry = await self._session.execute(stmt)
        return res_retry.scalar_one()

    async def get_list_by_name(
        self,
        *,
        household_id: uuid.UUID,
        name: str,
    ) -> SharedList | None:
        stmt = select(SharedList).where(
            SharedList.household_id == household_id,
            SharedList.name == name,
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def add_or_update_item(
        self,
        *,
        list_id: uuid.UUID,
        item_name: str,
        quantity: str | None,
        added_by: uuid.UUID | None,
    ) -> SharedListItem:
        # Check for existing unchecked item to dedupe/merge
        stmt = select(SharedListItem).where(
            SharedListItem.list_id == list_id,
            SharedListItem.checked.is_(False),
            func.lower(SharedListItem.item_name) == func.lower(item_name),
        )
        res = await self._session.execute(stmt)
        existing = res.scalar_one_or_none()

        now = datetime.now(UTC)
        if existing:
            # Last-write-wins update
            if quantity:
                existing.quantity = quantity
            existing.added_by = added_by
            existing.updated_at = now
            await self._session.flush()
            return existing

        item = SharedListItem(
            id=uuid.uuid4(),
            list_id=list_id,
            item_name=item_name,
            quantity=quantity,
            checked=False,
            added_by=added_by,
            created_at=now,
            updated_at=now,
        )
        self._session.add(item)
        await self._session.flush()
        return item

    async def get_list_items(
        self,
        *,
        list_id: uuid.UUID,
        include_checked: bool = True,
    ) -> list[SharedListItem]:
        stmt = select(SharedListItem).where(SharedListItem.list_id == list_id)
        if not include_checked:
            stmt = stmt.where(SharedListItem.checked.is_(False))
        stmt = stmt.order_by(SharedListItem.checked.asc(), SharedListItem.created_at.asc())
        res = await self._session.execute(stmt)
        return list(res.scalars().all())

    async def find_item_by_name(
        self,
        *,
        list_id: uuid.UUID,
        item_name: str,
    ) -> SharedListItem | None:
        stmt = (
            select(SharedListItem)
            .where(
                SharedListItem.list_id == list_id,
                func.lower(SharedListItem.item_name) == func.lower(item_name),
            )
            .order_by(SharedListItem.checked.asc())
        )
        res = await self._session.execute(stmt)
        return res.scalars().first()

    async def check_off_item(
        self,
        *,
        item_id: uuid.UUID,
    ) -> SharedListItem | None:
        now = datetime.now(UTC)
        stmt = (
            update(SharedListItem)
            .where(SharedListItem.id == item_id)
            .values(checked=True, updated_at=now)
            .returning(SharedListItem)
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def remove_item(
        self,
        *,
        item_id: uuid.UUID,
    ) -> bool:
        stmt = (
            delete(SharedListItem).where(SharedListItem.id == item_id).returning(SharedListItem.id)
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none() is not None

    async def clear_checked_items(
        self,
        *,
        list_id: uuid.UUID,
    ) -> int:
        stmt = (
            delete(SharedListItem)
            .where(
                SharedListItem.list_id == list_id,
                SharedListItem.checked.is_(True),
            )
            .returning(SharedListItem.id)
        )
        res = await self._session.execute(stmt)
        return len(res.scalars().all())
