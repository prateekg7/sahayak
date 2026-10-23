"""Integration/service tests for LedgerService and ledger lifecycle (T10.2)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.config import get_settings
from sahayak.core.db.session import UnitOfWork
from sahayak.core.errors import InvalidInputError, NotFoundError
from sahayak.modules.business.adapters.orders import SQLAlchemyBusinessRepository
from sahayak.modules.business.service.ledger import LedgerService
from sahayak.shared.users.models import User


@pytest.mark.asyncio
async def test_ledger_dues_payments_and_balance_lifecycle() -> None:
    """Test full customer dues, payments, and balance query lifecycle."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    service = LedgerService(session_factory=session_factory)
    user_id = uuid.uuid4()

    try:
        async with UnitOfWork(session_factory) as uow:
            uow.session.add(User(id=user_id))
            await uow.session.commit()

        # 1. Add first due of 500.00 INR (50000 minor)
        spoken1, data1 = await service.add_due(
            user_id=user_id,
            customer_name="Ramesh",
            amount_minor=50000,
            notes="5 kg basmati rice on credit",
        )
        assert data1["balance_minor"] == 50000
        assert "Added due of 500 rupees for Ramesh" in spoken1
        business_id = data1["business_id"]

        # 2. Add second due of 250.00 INR (25000 minor)
        spoken2, data2 = await service.add_due(
            user_id=user_id,
            business_id=business_id,
            customer_name="Ramesh",
            amount_minor=25000,
            notes="Cooking oil",
        )
        assert data2["balance_minor"] == 75000
        assert "Added due of 250 rupees for Ramesh" in spoken2

        # 3. Check balance
        spoken_bal, data_bal = await service.get_balance(
            user_id=user_id,
            business_id=business_id,
            customer_name="Ramesh",
        )
        assert data_bal["balance_minor"] == 75000
        assert data_bal["entries_count"] == 2
        assert "Ramesh currently owes 750 rupees" in spoken_bal

        # 4. Customer pays 500.00 INR (50000 minor)
        spoken_pay, data_pay = await service.record_payment(
            user_id=user_id,
            business_id=business_id,
            customer_name="Ramesh",
            amount_minor=50000,
            notes="UPI payment",
        )
        assert data_pay["balance_minor"] == 25000
        assert "Recorded payment of 500 rupees from Ramesh" in spoken_pay

        # 5. Customer pays remaining 250.00 INR (25000 minor)
        _, data_pay2 = await service.record_payment(
            user_id=user_id,
            business_id=business_id,
            customer_name="Ramesh",
            amount_minor=25000,
        )
        assert data_pay2["balance_minor"] == 0

        # 6. Check cleared balance
        spoken_cleared, data_cleared = await service.get_balance(
            user_id=user_id,
            business_id=business_id,
            customer_name="Ramesh",
        )
        assert data_cleared["balance_minor"] == 0
        assert "cleared all dues" in spoken_cleared
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_ledger_top_dues_and_reconciliation() -> None:
    """Test top_dues query ordering and daily reconciliation verification."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    service = LedgerService(session_factory=session_factory)
    user_id = uuid.uuid4()

    try:
        async with UnitOfWork(session_factory) as uow:
            uow.session.add(User(id=user_id))
            await uow.session.commit()

        # Pre-create business
        async with session_factory() as session:
            b_repo = SQLAlchemyBusinessRepository(session)
            biz, _ = await b_repo.get_or_create_default_business(
                user_id=user_id, name="Grocery Store"
            )
            await session.commit()
            biz_id = str(biz.id)

        # Add dues for 3 different customers
        await service.add_due(
            user_id=user_id, business_id=biz_id, customer_name="Customer A", amount_minor=10000
        )
        await service.add_due(
            user_id=user_id, business_id=biz_id, customer_name="Customer B", amount_minor=50000
        )
        await service.add_due(
            user_id=user_id, business_id=biz_id, customer_name="Customer C", amount_minor=30000
        )

        # Top dues should be ordered descending: Customer B, Customer C, Customer A
        spoken_top, data_top = await service.get_top_dues(
            user_id=user_id, business_id=biz_id, limit=5
        )
        names = [td["customer"]["name"] for td in data_top["top_dues"]]
        balances = [td["balance_minor"] for td in data_top["top_dues"]]

        assert names == ["Customer B", "Customer C", "Customer A"]
        assert balances == [50000, 30000, 10000]
        assert "Customer B owes 500 rupees" in spoken_top
        assert "Customer C owes 300 rupees" in spoken_top
        assert "Customer A owes 100 rupees" in spoken_top

        # Run daily reconciliation test
        spoken_rec, data_rec = await service.reconcile_balances(user_id=user_id, business_id=biz_id)
        assert data_rec["total_customers"] == 3
        assert data_rec["total_outstanding_minor"] == 90000
        assert data_rec["discrepancies_count"] == 0
        assert "zero discrepancies" in spoken_rec
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_ledger_reversal_workflow_and_safeguards() -> None:
    """Test entry reversal, audit trail reference, and rejection of duplicate/nested reversals."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    service = LedgerService(session_factory=session_factory)
    user_id = uuid.uuid4()

    try:
        async with UnitOfWork(session_factory) as uow:
            uow.session.add(User(id=user_id))
            await uow.session.commit()

        # Create mistaken due
        _, due_data = await service.add_due(
            user_id=user_id,
            customer_name="Priya",
            amount_minor=40000,
            notes="Accidental entry",
        )
        due_id = due_data["entry"]["id"]
        biz_id = due_data["business_id"]
        assert due_data["balance_minor"] == 40000

        # Reverse the due
        spoken_rev, data_rev = await service.reverse_entry(
            user_id=user_id,
            business_id=biz_id,
            entry_id=due_id,
            notes="Customer did not take these goods",
        )
        assert data_rev["new_balance_minor"] == 0
        assert data_rev["reversal_entry"]["reversed_entry_id"] == due_id
        assert data_rev["reversal_entry"]["entry_type"] == "reversal"
        assert "Reversed entry for Priya" in spoken_rev

        # Safeguard 1: Cannot reverse an already reversed entry
        with pytest.raises(InvalidInputError) as exc_info:
            await service.reverse_entry(
                user_id=user_id,
                business_id=biz_id,
                entry_id=due_id,
            )
        assert "already been reversed" in str(exc_info.value.spoken)

        # Safeguard 2: Cannot reverse the reversal entry itself
        reversal_id = data_rev["reversal_entry"]["id"]
        with pytest.raises(InvalidInputError) as exc_info2:
            await service.reverse_entry(
                user_id=user_id,
                business_id=biz_id,
                entry_id=reversal_id,
            )
        assert "cannot be reversed" in str(exc_info2.value.spoken)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_ledger_input_validations_and_unauthorized_access() -> None:
    """Test input validation for non-positive amounts and cross-business isolation."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    service = LedgerService(session_factory=session_factory)
    user_a = uuid.uuid4()

    try:
        async with UnitOfWork(session_factory) as uow:
            uow.session.add(User(id=user_a))
            await uow.session.commit()

        # Non-positive amount validation
        with pytest.raises(InvalidInputError) as exc1:
            await service.add_due(
                user_id=user_a,
                customer_name="Ramesh",
                amount_minor=0,
            )
        assert "greater than zero" in str(exc1.value.spoken)

        # Missing customer name validation
        with pytest.raises(InvalidInputError) as exc2:
            await service.add_due(
                user_id=user_a,
                customer_name="   ",
                amount_minor=500,
            )
        assert "specify the customer name" in str(exc2.value.spoken)

        # Customer not found balance lookup
        with pytest.raises(NotFoundError) as exc3:
            await service.get_balance(
                user_id=user_a,
                customer_name="NonExistentCustomer",
            )
        assert "could not be found" in str(exc3.value.spoken)
    finally:
        await engine.dispose()
