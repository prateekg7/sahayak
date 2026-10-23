"""SQLAlchemy implementation of SplitBillRepositoryPort (T6.3)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sahayak.modules.finance.models import (
    Group,
    GroupMember,
    Settlement,
    SharedExpense,
)


class SQLAlchemySplitBillRepository:
    """Repository managing bill splitting groups, expenses, and settlements."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_group(
        self,
        user_id: uuid.UUID,
        name: str,
        currency: str = "INR",
        members: list[str] | None = None,
    ) -> Group:
        group = Group(
            user_id=user_id,
            name=name.strip(),
            currency=currency.upper().strip(),
        )
        self.session.add(group)
        await self.session.flush()

        initial_members = set(members or [])
        initial_members.add("You")
        for m in initial_members:
            if m.strip():
                member = GroupMember(
                    group_id=group.id,
                    name=m.strip(),
                )
                self.session.add(member)

        await self.session.flush()
        return group

    async def get_group_by_name(self, user_id: uuid.UUID, name: str) -> Group | None:
        stmt = select(Group).where(
            Group.user_id == user_id,
            Group.name.ilike(name.strip()),
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_group(self, user_id: uuid.UUID, group_id: uuid.UUID) -> Group | None:
        stmt = select(Group).where(
            Group.user_id == user_id,
            Group.id == group_id,
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_groups(self, user_id: uuid.UUID) -> list[Group]:
        stmt = select(Group).where(Group.user_id == user_id).order_by(Group.created_at.desc())
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def get_group_members(self, group_id: uuid.UUID) -> list[GroupMember]:
        stmt = (
            select(GroupMember)
            .where(GroupMember.group_id == group_id)
            .order_by(GroupMember.name.asc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def add_group_members(
        self,
        group_id: uuid.UUID,
        member_names: list[str],
    ) -> list[GroupMember]:
        existing_stmt = select(GroupMember.name).where(GroupMember.group_id == group_id)
        existing_res = await self.session.execute(existing_stmt)
        existing_names = {n.lower() for n in existing_res.scalars().all()}

        added: list[GroupMember] = []
        for name in member_names:
            clean = name.strip()
            if clean and clean.lower() not in existing_names:
                member = GroupMember(group_id=group_id, name=clean)
                self.session.add(member)
                added.append(member)
                existing_names.add(clean.lower())

        if added:
            await self.session.flush()
        return added

    async def create_shared_expense(
        self,
        group_id: uuid.UUID,
        payer_name: str,
        total_minor: int,
        description: str,
        split_data: dict[str, int],
    ) -> SharedExpense:
        expense = SharedExpense(
            group_id=group_id,
            payer_name=payer_name.strip(),
            total_minor=total_minor,
            description=description.strip(),
            split_data=split_data,
        )
        self.session.add(expense)
        await self.session.flush()
        return expense

    async def list_shared_expenses(self, group_id: uuid.UUID) -> list[SharedExpense]:
        stmt = (
            select(SharedExpense)
            .where(SharedExpense.group_id == group_id)
            .order_by(SharedExpense.created_at.asc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def create_settlement(
        self,
        group_id: uuid.UUID,
        from_name: str,
        to_name: str,
        amount_minor: int,
    ) -> Settlement:
        settlement = Settlement(
            group_id=group_id,
            from_name=from_name.strip(),
            to_name=to_name.strip(),
            amount_minor=amount_minor,
        )
        self.session.add(settlement)
        await self.session.flush()
        return settlement

    async def list_settlements(self, group_id: uuid.UUID) -> list[Settlement]:
        stmt = (
            select(Settlement)
            .where(Settlement.group_id == group_id)
            .order_by(Settlement.settled_at.asc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())
