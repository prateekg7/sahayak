"""SQLAlchemy implementation of ExpenseRepositoryPort (T6.1)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sahayak.modules.finance.models import Expense


class SQLAlchemyExpenseRepository:
    """Repository managing expense persistence and spending aggregates."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_expense(
        self,
        user_id: uuid.UUID,
        amount_minor: int,
        currency: str,
        category: str,
        note: str | None = None,
        occurred_at: datetime | None = None,
    ) -> Expense:
        """Create and persist a new expense."""
        expense = Expense(
            user_id=user_id,
            amount_minor=amount_minor,
            currency=currency.upper().strip(),
            category=category.lower().strip(),
            note=note.strip() if note else None,
            occurred_at=occurred_at or datetime.now(UTC),
            is_deleted=False,
        )
        self.session.add(expense)
        await self.session.flush()
        return expense

    async def get_expense(self, user_id: uuid.UUID, expense_id: uuid.UUID) -> Expense | None:
        """Retrieve an active expense by ID, scoped by user_id."""
        stmt = select(Expense).where(
            Expense.id == expense_id,
            Expense.user_id == user_id,
            Expense.is_deleted.is_(False),
        )
        res = await self.session.execute(stmt)
        return res.scalars().first()

    async def get_latest_expense(self, user_id: uuid.UUID) -> Expense | None:
        """Retrieve the most recently logged active expense for a user."""
        stmt = (
            select(Expense)
            .where(
                Expense.user_id == user_id,
                Expense.is_deleted.is_(False),
            )
            .order_by(desc(Expense.created_at))
            .limit(1)
        )
        res = await self.session.execute(stmt)
        return res.scalars().first()

    async def list_expenses(
        self,
        user_id: uuid.UUID,
        category: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 10,
    ) -> list[Expense]:
        """List active expenses for a user, ordered by occurred_at DESC."""
        stmt = select(Expense).where(
            Expense.user_id == user_id,
            Expense.is_deleted.is_(False),
        )
        if category:
            stmt = stmt.where(Expense.category == category.lower().strip())
        if since:
            stmt = stmt.where(Expense.occurred_at >= since)
        if until:
            stmt = stmt.where(Expense.occurred_at <= until)

        stmt = stmt.order_by(desc(Expense.occurred_at), desc(Expense.created_at)).limit(limit)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def soft_delete_expense(self, user_id: uuid.UUID, expense_id: uuid.UUID) -> bool:
        """Soft delete an expense by marking is_deleted = True."""
        stmt = select(Expense).where(
            Expense.id == expense_id,
            Expense.user_id == user_id,
            Expense.is_deleted.is_(False),
        )
        res = await self.session.execute(stmt)
        record = res.scalars().first()
        if record is None:
            return False

        record.is_deleted = True
        await self.session.flush()
        return True

    async def undo_last_expense(self, user_id: uuid.UUID) -> Expense | None:
        """Undo the most recent active expense for a user."""
        latest = await self.get_latest_expense(user_id)
        if latest is None:
            return None

        latest.is_deleted = True
        await self.session.flush()
        return latest

    async def get_total_spending(
        self,
        user_id: uuid.UUID,
        currency: str,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> int:
        """Sum total spending in minor units for a user and currency."""
        stmt = select(func.coalesce(func.sum(Expense.amount_minor), 0)).where(
            Expense.user_id == user_id,
            Expense.currency == currency.upper().strip(),
            Expense.is_deleted.is_(False),
        )
        if since:
            stmt = stmt.where(Expense.occurred_at >= since)
        if until:
            stmt = stmt.where(Expense.occurred_at <= until)

        res = await self.session.execute(stmt)
        val = res.scalar()
        return int(val) if val is not None else 0

    async def get_category_spending(
        self,
        user_id: uuid.UUID,
        category: str,
        currency: str,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> int:
        """Sum total spending in minor units for a user, category, and currency."""
        stmt = select(func.coalesce(func.sum(Expense.amount_minor), 0)).where(
            Expense.user_id == user_id,
            Expense.category == category.lower().strip(),
            Expense.currency == currency.upper().strip(),
            Expense.is_deleted.is_(False),
        )
        if since:
            stmt = stmt.where(Expense.occurred_at >= since)
        if until:
            stmt = stmt.where(Expense.occurred_at <= until)

        res = await self.session.execute(stmt)
        val = res.scalar()
        return int(val) if val is not None else 0
