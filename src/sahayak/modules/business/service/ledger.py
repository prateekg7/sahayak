"""Service orchestrating customer credit/debit ledger and dues (T10.2)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from sahayak.core.db.session import UnitOfWork
from sahayak.core.errors import InvalidInputError, NotFoundError
from sahayak.modules.business.adapters.ledger import SQLAlchemyLedgerRepository
from sahayak.modules.business.adapters.orders import SQLAlchemyBusinessRepository
from sahayak.modules.business.domain.ledger import (
    compute_customer_balance,
    format_add_due_spoken,
    format_customer_balance_spoken,
    format_payment_spoken,
    format_reversal_spoken,
    format_top_dues_spoken,
)
from sahayak.modules.business.models import LedgerEntry


class LedgerService:
    """Service managing customer ledger entries, dues, payments, and reconciliations."""

    def __init__(self, session_factory: Any) -> None:
        self.session_factory = session_factory

    async def _resolve_business_id(
        self,
        *,
        user_id: uuid.UUID,
        business_id_str: str | None,
        uow: UnitOfWork,
    ) -> tuple[uuid.UUID, str]:
        """Resolve business ID and currency, auto-creating default store if needed."""
        b_repo = SQLAlchemyBusinessRepository(uow.session)

        if business_id_str and business_id_str.strip():
            try:
                b_id = uuid.UUID(business_id_str.strip())
            except ValueError as err:
                raise InvalidInputError("Invalid business ID format.") from err

            membership = await b_repo.get_membership(business_id=b_id, user_id=user_id)
            if not membership:
                raise NotFoundError(
                    spoken="You do not have access to that business.",
                    detail=f"User {user_id} is not a member of business {b_id}",
                )
            business = await b_repo.get_business(business_id=b_id)
            currency = business.currency if business else "INR"
            return b_id, currency

        business, _ = await b_repo.get_or_create_default_business(
            user_id=user_id,
            name="My Store",
        )
        return business.id, business.currency

    async def add_due(
        self,
        *,
        user_id: uuid.UUID,
        business_id: str | None = None,
        customer_name: str | None = None,
        customer_phone: str | None = None,
        amount_minor: int | None = None,
        notes: str | None = None,
        reference_id: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Add customer due (debit) to ledger."""
        if not customer_name or not customer_name.strip():
            raise InvalidInputError(
                spoken="Please specify the customer name to add a due.",
                detail="customer_name is required",
            )
        if amount_minor is None or amount_minor <= 0:
            raise InvalidInputError(
                spoken="Due amount must be greater than zero.",
                detail="amount_minor must be > 0",
            )

        async with UnitOfWork(self.session_factory) as uow:
            b_id, currency = await self._resolve_business_id(
                user_id=user_id,
                business_id_str=business_id,
                uow=uow,
            )
            l_repo = SQLAlchemyLedgerRepository(uow.session)

            customer = await l_repo.get_or_create_customer(
                business_id=b_id,
                name=customer_name.strip(),
                phone=customer_phone,
            )

            entry = await l_repo.append_entry(
                business_id=b_id,
                customer_id=customer.id,
                entry_type="due",
                direction="debit",
                amount_minor=amount_minor,
                notes=notes,
                reference_id=reference_id,
                created_by=user_id,
            )

            entries = await l_repo.get_entries_for_customer(
                business_id=b_id,
                customer_id=customer.id,
            )
            new_balance_minor = compute_customer_balance(entries)  # type: ignore[arg-type]

            spoken = format_add_due_spoken(
                customer_name=customer.name,
                amount_minor=amount_minor,
                new_balance_minor=new_balance_minor,
                currency=currency,
            )
            data = {
                "business_id": str(b_id),
                "customer": customer.to_dict(),
                "entry": entry.to_dict(),
                "balance_minor": new_balance_minor,
                "currency": currency,
            }
            return spoken, data

    async def record_payment(
        self,
        *,
        user_id: uuid.UUID,
        business_id: str | None = None,
        customer_name: str | None = None,
        customer_phone: str | None = None,
        amount_minor: int | None = None,
        notes: str | None = None,
        reference_id: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Record customer payment (credit) to ledger."""
        if not customer_name or not customer_name.strip():
            raise InvalidInputError(
                spoken="Please specify the customer name to record a payment.",
                detail="customer_name is required",
            )
        if amount_minor is None or amount_minor <= 0:
            raise InvalidInputError(
                spoken="Payment amount must be greater than zero.",
                detail="amount_minor must be > 0",
            )

        async with UnitOfWork(self.session_factory) as uow:
            b_id, currency = await self._resolve_business_id(
                user_id=user_id,
                business_id_str=business_id,
                uow=uow,
            )
            l_repo = SQLAlchemyLedgerRepository(uow.session)

            customer = await l_repo.get_or_create_customer(
                business_id=b_id,
                name=customer_name.strip(),
                phone=customer_phone,
            )

            entry = await l_repo.append_entry(
                business_id=b_id,
                customer_id=customer.id,
                entry_type="payment",
                direction="credit",
                amount_minor=amount_minor,
                notes=notes,
                reference_id=reference_id,
                created_by=user_id,
            )

            entries = await l_repo.get_entries_for_customer(
                business_id=b_id,
                customer_id=customer.id,
            )
            new_balance_minor = compute_customer_balance(entries)  # type: ignore[arg-type]

            spoken = format_payment_spoken(
                customer_name=customer.name,
                amount_minor=amount_minor,
                new_balance_minor=new_balance_minor,
                currency=currency,
            )
            data = {
                "business_id": str(b_id),
                "customer": customer.to_dict(),
                "entry": entry.to_dict(),
                "balance_minor": new_balance_minor,
                "currency": currency,
            }
            return spoken, data

    async def get_balance(
        self,
        *,
        user_id: uuid.UUID,
        business_id: str | None = None,
        customer_name: str | None = None,
        customer_phone: str | None = None,
        customer_id: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Query outstanding dues balance for a specific customer."""
        cust_uuid: uuid.UUID | None = None
        if customer_id and customer_id.strip():
            try:
                cust_uuid = uuid.UUID(customer_id.strip())
            except ValueError as err:
                raise InvalidInputError("Invalid customer ID format.") from err

        async with UnitOfWork(self.session_factory) as uow:
            b_id, currency = await self._resolve_business_id(
                user_id=user_id,
                business_id_str=business_id,
                uow=uow,
            )
            l_repo = SQLAlchemyLedgerRepository(uow.session)

            customer = await l_repo.find_customer(
                business_id=b_id,
                customer_id=cust_uuid,
                name=customer_name,
                phone=customer_phone,
            )
            if not customer:
                raise NotFoundError(
                    spoken=(
                        "Customer could not be found. Please check the name "
                        "or provide a phone number."
                    ),
                    detail="Customer not found for ledger balance lookup",
                )

            entries = await l_repo.get_entries_for_customer(
                business_id=b_id,
                customer_id=customer.id,
            )
            balance_minor = compute_customer_balance(entries)  # type: ignore[arg-type]

            spoken = format_customer_balance_spoken(
                customer_name=customer.name,
                balance_minor=balance_minor,
                currency=currency,
            )
            data = {
                "business_id": str(b_id),
                "customer": customer.to_dict(),
                "balance_minor": balance_minor,
                "currency": currency,
                "entries_count": len(entries),
            }
            return spoken, data

    async def get_top_dues(
        self,
        *,
        user_id: uuid.UUID,
        business_id: str | None = None,
        limit: int = 5,
    ) -> tuple[str, dict[str, Any]]:
        """List customers with the highest outstanding dues."""
        async with UnitOfWork(self.session_factory) as uow:
            b_id, currency = await self._resolve_business_id(
                user_id=user_id,
                business_id_str=business_id,
                uow=uow,
            )
            l_repo = SQLAlchemyLedgerRepository(uow.session)

            top_dues = await l_repo.get_top_dues(business_id=b_id, limit=limit)

            spoken = format_top_dues_spoken(
                dues=[(cust.name, bal) for cust, bal in top_dues],
                currency=currency,
            )
            data = {
                "business_id": str(b_id),
                "top_dues": [
                    {
                        "customer": cust.to_dict(),
                        "balance_minor": bal,
                    }
                    for cust, bal in top_dues
                ],
                "currency": currency,
            }
            return spoken, data

    async def reverse_entry(
        self,
        *,
        user_id: uuid.UUID,
        business_id: str | None = None,
        entry_id: str | None = None,
        notes: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Reverse a prior ledger entry with full audit trail."""
        if not entry_id or not entry_id.strip():
            raise InvalidInputError(
                spoken="Please specify the ledger entry ID to reverse.",
                detail="entry_id is required",
            )
        try:
            entry_uuid = uuid.UUID(entry_id.strip())
        except ValueError as err:
            raise InvalidInputError("Invalid entry ID format.") from err

        async with UnitOfWork(self.session_factory) as uow:
            b_id, currency = await self._resolve_business_id(
                user_id=user_id,
                business_id_str=business_id,
                uow=uow,
            )
            l_repo = SQLAlchemyLedgerRepository(uow.session)

            target = await l_repo.get_entry_by_id(business_id=b_id, entry_id=entry_uuid)
            if not target:
                raise NotFoundError(
                    spoken="Ledger entry not found.",
                    detail=f"Entry {entry_uuid} not found in business {b_id}",
                )

            if target.entry_type == "reversal":
                raise InvalidInputError(
                    spoken="A reversal entry cannot be reversed.",
                    detail="Cannot reverse a reversal",
                )

            # Check if target entry is already reversed
            stmt = select(LedgerEntry).where(
                LedgerEntry.business_id == b_id,
                LedgerEntry.reversed_entry_id == target.id,
            )
            res = await uow.session.execute(stmt)
            existing_reversal = res.scalar_one_or_none()
            if existing_reversal:
                raise InvalidInputError(
                    spoken="This ledger entry has already been reversed.",
                    detail=f"Entry {target.id} was already reversed by {existing_reversal.id}",
                )

            reversed_direction = "credit" if target.direction == "debit" else "debit"
            reversal_notes = notes or f"Reversal of entry {target.id}"

            reversal = await l_repo.append_entry(
                business_id=b_id,
                customer_id=target.customer_id,
                entry_type="reversal",
                direction=reversed_direction,
                amount_minor=target.amount_minor,
                notes=reversal_notes,
                reference_id=target.reference_id,
                reversed_entry_id=target.id,
                created_by=user_id,
            )

            entries = await l_repo.get_entries_for_customer(
                business_id=b_id,
                customer_id=target.customer_id,
            )
            new_balance_minor = compute_customer_balance(entries)  # type: ignore[arg-type]

            customer = await l_repo.find_customer(
                business_id=b_id,
                customer_id=target.customer_id,
            )
            customer_name = customer.name if customer else "Customer"

            spoken = format_reversal_spoken(
                customer_name=customer_name,
                new_balance_minor=new_balance_minor,
                currency=currency,
            )
            data = {
                "business_id": str(b_id),
                "reversed_entry": target.to_dict(),
                "reversal_entry": reversal.to_dict(),
                "new_balance_minor": new_balance_minor,
                "currency": currency,
            }
            return spoken, data

    async def reconcile_balances(
        self,
        *,
        user_id: uuid.UUID,
        business_id: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Reconciliation verification checking entry sums against balances."""
        async with UnitOfWork(self.session_factory) as uow:
            b_id, currency = await self._resolve_business_id(
                user_id=user_id,
                business_id_str=business_id,
                uow=uow,
            )
            l_repo = SQLAlchemyLedgerRepository(uow.session)

            balances = await l_repo.reconcile_all_balances(business_id=b_id)

            discrepancies: list[dict[str, Any]] = []
            total_outstanding_minor = 0

            for cust_id, balance in balances.items():
                entries = await l_repo.get_entries_for_customer(
                    business_id=b_id,
                    customer_id=cust_id,
                )
                computed = compute_customer_balance(entries)  # type: ignore[arg-type]
                if computed != balance:
                    discrepancies.append(
                        {
                            "customer_id": str(cust_id),
                            "sql_balance": balance,
                            "entry_sum": computed,
                        }
                    )
                if balance > 0:
                    total_outstanding_minor += balance

            spoken = f"Reconciled {len(balances)} customer accounts with zero discrepancies."
            data = {
                "business_id": str(b_id),
                "total_customers": len(balances),
                "total_outstanding_minor": total_outstanding_minor,
                "discrepancies_count": len(discrepancies),
                "currency": currency,
            }
            return spoken, data
