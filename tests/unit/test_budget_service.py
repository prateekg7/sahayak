"""Unit tests for BudgetService lifecycle, run-rate tracking, and error handling (T6.2)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.config import get_settings
from sahayak.core.db.session import UnitOfWork
from sahayak.core.errors import InvalidInputError, NotFoundError
from sahayak.modules.finance.schemas import BudgetAction, BudgetRequest
from sahayak.modules.finance.service.budgets import BudgetService
from sahayak.modules.finance.service.expenses import ExpenseService
from sahayak.shared.users.models import User


@pytest.mark.asyncio
async def test_budget_service_lifecycle() -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    user_id = uuid.uuid4()
    fixed_now = datetime(2026, 10, 15, 12, 0, 0, tzinfo=UTC)

    budget_service = BudgetService(
        session_factory=session_factory,
        clock=lambda: fixed_now,
    )
    expense_service = ExpenseService(
        session_factory=session_factory,
        clock=lambda: fixed_now,
    )

    try:
        async with UnitOfWork(session_factory) as uow:
            uow.session.add(User(id=user_id))
            await uow.session.flush()

        # 1. Set groceries budget
        req_set = BudgetRequest(
            action=BudgetAction.SET,
            category="groceries",
            amount="5000",
            currency="INR",
        )
        res_set, spoken_set = await budget_service.execute(user_id, req_set)
        assert "Your monthly groceries budget has been set to 5000 rupees." in spoken_set
        assert res_set.budget is not None
        assert res_set.budget.amount_minor == 500000

        # 2. Check initial status with 0 spending
        req_status = BudgetRequest(
            action=BudgetAction.STATUS,
            category="groceries",
        )
        res_stat, spoken_stat = await budget_service.execute(user_id, req_status)
        assert res_stat.status is not None
        assert res_stat.status.spent_minor == 0
        assert res_stat.status.remaining_minor == 500000
        assert "5000 rupees remaining" in spoken_stat

        # 3. Add an expense of 2000 INR in groceries
        await expense_service.add_expense(
            user_id=user_id,
            amount=2000,
            currency="INR",
            category="groceries",
        )

        # Check status again
        res_stat2, spoken_stat2 = await budget_service.execute(user_id, req_status)
        assert res_stat2.status is not None
        assert res_stat2.status.spent_minor == 200000
        assert res_stat2.status.remaining_minor == 300000
        assert "spent 2000 rupees of your 5000 rupees groceries budget" in spoken_stat2

        # 4. Set dining budget
        await budget_service.execute(
            user_id,
            BudgetRequest(
                action=BudgetAction.SET,
                category="dining",
                amount=1500,
                currency="INR",
            ),
        )

        # 5. List budgets
        res_list, spoken_list = await budget_service.execute(
            user_id,
            BudgetRequest(action=BudgetAction.LIST),
        )
        assert res_list.count == 2
        assert "2 category budgets" in spoken_list

        # 6. Remove dining budget
        res_rem, spoken_rem = await budget_service.execute(
            user_id,
            BudgetRequest(action=BudgetAction.REMOVE, category="dining"),
        )
        assert "Your dining budget has been removed." in spoken_rem

        # 7. Check status of removed dining budget -> NotFoundError
        with pytest.raises(NotFoundError):
            await budget_service.execute(
                user_id,
                BudgetRequest(action=BudgetAction.STATUS, category="dining"),
            )

    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_budget_service_validation_errors() -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    user_id = uuid.uuid4()
    service = BudgetService(session_factory=session_factory)

    try:
        # Missing category on set
        with pytest.raises(InvalidInputError):
            await service.execute(
                user_id,
                BudgetRequest(action=BudgetAction.SET, category="", amount=500),
            )

        # Missing amount on set
        with pytest.raises(InvalidInputError):
            await service.execute(
                user_id,
                BudgetRequest(action=BudgetAction.SET, category="books", amount=None),
            )

        # Non-positive amount
        with pytest.raises(InvalidInputError):
            await service.execute(
                user_id,
                BudgetRequest(action=BudgetAction.SET, category="books", amount=0),
            )

        # Status for non-existent category
        with pytest.raises(NotFoundError):
            await service.execute(
                user_id,
                BudgetRequest(action=BudgetAction.STATUS, category="non_existent_category"),
            )

        # Remove non-existent category
        with pytest.raises(NotFoundError):
            await service.execute(
                user_id,
                BudgetRequest(action=BudgetAction.REMOVE, category="non_existent_category"),
            )

    finally:
        await engine.dispose()
