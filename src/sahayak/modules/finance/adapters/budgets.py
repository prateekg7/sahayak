"""SQLAlchemy implementation of BudgetRepositoryPort (T6.2)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sahayak.modules.finance.models import Budget


class SQLAlchemyBudgetRepository:
    """Repository managing budget persistence."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert_budget(
        self,
        user_id: uuid.UUID,
        category: str,
        amount_minor: int,
        currency: str = "INR",
    ) -> Budget:
        """Create or update an active budget for a user and category."""
        norm_cat = category.lower().strip()
        norm_curr = currency.upper().strip()

        stmt = select(Budget).where(
            Budget.user_id == user_id,
            Budget.category == norm_cat,
        )
        res = await self.session.execute(stmt)
        budget = res.scalar_one_or_none()

        if budget is None:
            budget = Budget(
                user_id=user_id,
                category=norm_cat,
                amount_minor=amount_minor,
                currency=norm_curr,
                is_active=True,
            )
            self.session.add(budget)
        else:
            budget.amount_minor = amount_minor
            budget.currency = norm_curr
            budget.is_active = True
            budget.updated_at = datetime.now(UTC)

        await self.session.flush()
        return budget

    async def get_budget(self, user_id: uuid.UUID, category: str) -> Budget | None:
        """Retrieve an active budget for a user and category."""
        stmt = select(Budget).where(
            Budget.user_id == user_id,
            Budget.category == category.lower().strip(),
            Budget.is_active.is_(True),
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_budgets(
        self,
        user_id: uuid.UUID,
        is_active: bool = True,
    ) -> list[Budget]:
        """List category budgets for a user."""
        stmt = (
            select(Budget)
            .where(
                Budget.user_id == user_id,
                Budget.is_active.is_(is_active),
            )
            .order_by(Budget.category.asc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def remove_budget(self, user_id: uuid.UUID, category: str) -> bool:
        """Deactivate a category budget for a user."""
        stmt = select(Budget).where(
            Budget.user_id == user_id,
            Budget.category == category.lower().strip(),
            Budget.is_active.is_(True),
        )
        res = await self.session.execute(stmt)
        budget = res.scalar_one_or_none()
        if budget is None:
            return False

        budget.is_active = False
        budget.updated_at = datetime.now(UTC)
        await self.session.flush()
        return True
