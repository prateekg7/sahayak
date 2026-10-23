"""Unit tests for ExpenseService orchestration, undo operations, and list calculations (T6.1)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.config import get_settings
from sahayak.core.db.session import UnitOfWork
from sahayak.core.errors import InvalidInputError, NotFoundError
from sahayak.modules.finance.service.expenses import ExpenseService
from sahayak.shared.users.models import User


@pytest.mark.asyncio
async def test_expense_lifecycle_add_list_undo_delete() -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    user_id = uuid.uuid4()
    fixed_now = datetime(2026, 10, 23, 10, 0, 0, tzinfo=UTC)

    service = ExpenseService(
        session_factory=session_factory,
        clock=lambda: fixed_now,
    )

    try:
        # Seed user
        async with UnitOfWork(session_factory) as uow:
            uow.session.add(User(id=user_id))
            await uow.session.flush()

        # 1. Add first expense
        spoken_add1, data_add1, _ = await service.add_expense(
            user_id=user_id,
            amount=200,
            currency="INR",
            category="groceries",
            note="Milk and bread",
        )
        assert "Added 200 rupees for groceries." in spoken_add1
        assert data_add1.expense is not None
        assert data_add1.expense.amount_minor == 20000
        assert data_add1.expense.category == "groceries"
        exp1_id = data_add1.expense.id

        # 2. Add second expense
        spoken_add2, data_add2, _ = await service.add_expense(
            user_id=user_id,
            amount="50.50",
            currency="INR",
            category="transport",
            note="Bus ticket",
        )
        assert "Added 50 rupees and 50 paise for transport." in spoken_add2
        assert data_add2.expense is not None
        assert data_add2.expense.amount_minor == 5050

        # 3. List expenses
        spoken_list, data_list, _ = await service.list_expenses(user_id=user_id)
        assert "2 recent expenses totaling 250 rupees and 50 paise." in spoken_list
        assert data_list.count == 2
        assert data_list.total_amount_minor == 25050

        # 4. Undo last expense (undoes the 50.50 transport expense)
        spoken_undo, data_undo, _ = await service.undo_last_expense(user_id=user_id)
        assert "Undid your last expense of 50 rupees and 50 paise for transport." in spoken_undo
        assert data_undo.expense is not None
        assert data_undo.expense.amount_minor == 5050

        # Verify only first expense remains active
        _, data_list_after_undo, _ = await service.list_expenses(user_id=user_id)
        assert data_list_after_undo.count == 1
        assert data_list_after_undo.total_amount_minor == 20000
        assert data_list_after_undo.expenses[0].id == exp1_id

        # 5. Delete first expense by ID
        spoken_del, data_del, _ = await service.delete_expense(
            user_id=user_id,
            expense_id_str=exp1_id,
        )
        assert "Deleted the expense." in spoken_del
        assert data_del.count == 1

        # List now empty
        spoken_empty, data_empty, _ = await service.list_expenses(user_id=user_id)
        assert "not logged any expenses yet" in spoken_empty
        assert data_empty.count == 0

    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_expense_service_errors() -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    user_id = uuid.uuid4()
    service = ExpenseService(session_factory=session_factory)

    try:
        # Invalid amount
        with pytest.raises(InvalidInputError):
            await service.add_expense(user_id=user_id, amount=0)

        with pytest.raises(InvalidInputError):
            await service.add_expense(user_id=user_id, amount="-10")

        # Undo when no expenses
        with pytest.raises(NotFoundError):
            await service.undo_last_expense(user_id=user_id)

        # Delete invalid uuid
        with pytest.raises(InvalidInputError):
            await service.delete_expense(user_id=user_id, expense_id_str="not-a-uuid")

        # Delete non-existent expense
        with pytest.raises(NotFoundError):
            await service.delete_expense(user_id=user_id, expense_id_str=str(uuid.uuid4()))

    finally:
        await engine.dispose()
