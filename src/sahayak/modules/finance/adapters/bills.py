"""SQLAlchemy repository adapter for recurring bills and EMI due dates (T6.4)."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sahayak.modules.finance.models import Bill
from sahayak.modules.finance.ports import BillRepositoryPort


class SQLAlchemyBillRepository(BillRepositoryPort):
    """SQLAlchemy implementation of the BillRepositoryPort."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_bill(
        self,
        user_id: uuid.UUID,
        name: str,
        amount_minor: int,
        due_day: int,
        next_due_date: date,
        currency: str = "INR",
        frequency: str = "monthly",
    ) -> Bill:
        """Create and persist a new recurring bill."""
        bill = Bill(
            user_id=user_id,
            name=name.strip(),
            amount_minor=amount_minor,
            currency=currency.upper().strip(),
            frequency=frequency.lower().strip(),
            due_day=due_day,
            next_due_date=next_due_date,
            is_paid=False,
            is_active=True,
        )
        self.session.add(bill)
        await self.session.flush()
        return bill

    async def get_bill(self, user_id: uuid.UUID, bill_id: uuid.UUID) -> Bill | None:
        """Retrieve a bill by ID scoped by user_id."""
        stmt = select(Bill).where(
            Bill.id == bill_id,
            Bill.user_id == user_id,
        )
        res = await self.session.execute(stmt)
        return res.scalars().first()

    async def list_bills(
        self,
        user_id: uuid.UUID,
        is_active: bool = True,
        due_before: date | None = None,
    ) -> list[Bill]:
        """List bills for a user, ordered by next_due_date ASC."""
        stmt = select(Bill).where(
            Bill.user_id == user_id,
            Bill.is_active == is_active,
        )
        if due_before:
            stmt = stmt.where(Bill.next_due_date <= due_before)

        stmt = stmt.order_by(Bill.next_due_date.asc())
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def mark_bill_paid(
        self,
        user_id: uuid.UUID,
        bill_id: uuid.UUID,
        next_due_date: date,
    ) -> Bill | None:
        """Mark bill paid for the current cycle and roll forward next_due_date."""
        bill = await self.get_bill(user_id, bill_id)
        if bill is None:
            return None

        bill.next_due_date = next_due_date
        bill.is_paid = False  # Next cycle is pending
        await self.session.flush()
        return bill

    async def deactivate_bill(self, user_id: uuid.UUID, bill_id: uuid.UUID) -> bool:
        """Deactivate a recurring bill."""
        bill = await self.get_bill(user_id, bill_id)
        if bill is None:
            return False

        bill.is_active = False
        await self.session.flush()
        return True
