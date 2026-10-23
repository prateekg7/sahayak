"""SQLAlchemy repository for customer credit and debit ledger (T10.2)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sahayak.modules.business.models import Customer, LedgerEntry
from sahayak.modules.business.ports import LedgerRepositoryPort


class SQLAlchemyLedgerRepository(LedgerRepositoryPort):
    """Repository handling customer dues, payments, and ledger entries in PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create_customer(
        self,
        *,
        business_id: uuid.UUID,
        name: str,
        phone: str | None = None,
    ) -> Customer:
        """Find existing customer by name/phone or create new one."""
        clean_name = name.strip()
        clean_phone = phone.strip() if phone else None

        # Try match by phone first if provided
        if clean_phone:
            stmt = select(Customer).where(
                Customer.business_id == business_id,
                Customer.phone == clean_phone,
            )
            res = await self.session.execute(stmt)
            cust = res.scalar_one_or_none()
            if cust:
                return cust

        # Try match by case-insensitive name
        stmt = select(Customer).where(
            Customer.business_id == business_id,
            func.lower(Customer.name) == clean_name.lower(),
        )
        res = await self.session.execute(stmt)
        cust = res.scalar_one_or_none()
        if cust:
            if clean_phone and not cust.phone:
                cust.phone = clean_phone
                await self.session.flush()
            return cust

        # Create new customer
        now = datetime.now(UTC)
        cust = Customer(
            id=uuid.uuid4(),
            business_id=business_id,
            name=clean_name,
            phone=clean_phone,
            created_at=now,
        )
        self.session.add(cust)
        await self.session.flush()
        return cust

    async def find_customer(
        self,
        *,
        business_id: uuid.UUID,
        customer_id: uuid.UUID | None = None,
        name: str | None = None,
        phone: str | None = None,
    ) -> Customer | None:
        """Find a customer by ID, exact name, or phone."""
        if customer_id is not None:
            stmt = select(Customer).where(
                Customer.id == customer_id,
                Customer.business_id == business_id,
            )
            res = await self.session.execute(stmt)
            return res.scalar_one_or_none()

        if phone is not None and phone.strip():
            stmt = select(Customer).where(
                Customer.business_id == business_id,
                Customer.phone == phone.strip(),
            )
            res = await self.session.execute(stmt)
            cust = res.scalar_one_or_none()
            if cust:
                return cust

        if name is not None and name.strip():
            stmt = select(Customer).where(
                Customer.business_id == business_id,
                func.lower(Customer.name) == name.strip().lower(),
            )
            res = await self.session.execute(stmt)
            return res.scalar_one_or_none()

        return None

    async def append_entry(
        self,
        *,
        business_id: uuid.UUID,
        customer_id: uuid.UUID,
        entry_type: str,
        direction: str,
        amount_minor: int,
        notes: str | None = None,
        reference_id: str | None = None,
        reversed_entry_id: uuid.UUID | None = None,
        created_by: uuid.UUID | None = None,
    ) -> LedgerEntry:
        """Append an immutable ledger entry."""
        now = datetime.now(UTC)
        entry = LedgerEntry(
            id=uuid.uuid4(),
            business_id=business_id,
            customer_id=customer_id,
            entry_type=entry_type,
            direction=direction,
            amount_minor=amount_minor,
            notes=notes,
            reference_id=reference_id,
            reversed_entry_id=reversed_entry_id,
            created_by=created_by,
            created_at=now,
        )
        self.session.add(entry)
        await self.session.flush()
        await self.session.refresh(entry)
        return entry

    async def get_entries_for_customer(
        self,
        *,
        business_id: uuid.UUID,
        customer_id: uuid.UUID,
    ) -> list[LedgerEntry]:
        """Fetch all ledger entries for a customer in chronological order."""
        stmt = (
            select(LedgerEntry)
            .where(
                LedgerEntry.business_id == business_id,
                LedgerEntry.customer_id == customer_id,
            )
            .order_by(LedgerEntry.created_at.asc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def get_entry_by_id(
        self,
        *,
        business_id: uuid.UUID,
        entry_id: uuid.UUID,
    ) -> LedgerEntry | None:
        """Fetch a specific ledger entry by ID."""
        stmt = select(LedgerEntry).where(
            LedgerEntry.business_id == business_id,
            LedgerEntry.id == entry_id,
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_top_dues(
        self,
        *,
        business_id: uuid.UUID,
        limit: int = 5,
    ) -> list[tuple[Customer, int]]:
        """Fetch customers with highest outstanding dues (positive balance)."""
        balance_expr = func.sum(
            case(
                (LedgerEntry.direction == "debit", LedgerEntry.amount_minor),
                else_=-LedgerEntry.amount_minor,
            )
        )
        stmt = (
            select(Customer, balance_expr.label("balance"))
            .join(Customer, Customer.id == LedgerEntry.customer_id)
            .where(LedgerEntry.business_id == business_id)
            .group_by(Customer.id)
            .having(balance_expr > 0)
            .order_by(balance_expr.desc())
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        return [(row[0], int(row[1])) for row in res.all()]

    async def reconcile_all_balances(
        self,
        *,
        business_id: uuid.UUID,
    ) -> dict[uuid.UUID, int]:
        """Reconcile and compute current balances for all customers from ledger entries."""
        balance_expr = func.sum(
            case(
                (LedgerEntry.direction == "debit", LedgerEntry.amount_minor),
                else_=-LedgerEntry.amount_minor,
            )
        )
        stmt = (
            select(LedgerEntry.customer_id, balance_expr.label("balance"))
            .where(LedgerEntry.business_id == business_id)
            .group_by(LedgerEntry.customer_id)
        )
        res = await self.session.execute(stmt)
        return {row[0]: int(row[1]) for row in res.all()}
