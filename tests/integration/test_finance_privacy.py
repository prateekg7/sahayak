"""Integration tests for finance module GDPR privacy export and deletion (T6.1)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.config import get_settings
from sahayak.core.db.session import UnitOfWork
from sahayak.core.module import Deps
from sahayak.modules.finance.module import FinanceModule
from sahayak.modules.finance.service.expenses import ExpenseService
from sahayak.shared.users.models import User


@pytest.mark.asyncio
async def test_finance_privacy_export_and_delete() -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    user_id = uuid.uuid4()
    fin_module = FinanceModule()
    deps = Deps(session_factory=session_factory)
    fin_module._deps = deps

    service = ExpenseService(session_factory=session_factory)

    try:
        # Seed user
        async with UnitOfWork(session_factory) as uow:
            uow.session.add(User(id=user_id))
            await uow.session.flush()

        # Seed expenses and budget
        await service.add_expense(
            user_id=user_id,
            amount=500,
            currency="INR",
            category="groceries",
            note="Weekly shopping",
        )
        await service.add_expense(
            user_id=user_id,
            amount=120,
            currency="INR",
            category="transport",
            note="Metro card recharge",
        )

        from sahayak.modules.finance.service.budgets import BudgetService

        budget_service = BudgetService(session_factory=session_factory)
        from sahayak.modules.finance.schemas import BudgetAction, BudgetRequest

        await budget_service.execute(
            user_id,
            BudgetRequest(
                action=BudgetAction.SET,
                category="groceries",
                amount=5000,
                currency="INR",
            ),
        )

        from sahayak.modules.finance.service.split_bill import SplitBillService

        split_service = SplitBillService(session_factory=session_factory)
        from sahayak.modules.finance.schemas import SplitBillAction, SplitBillRequest

        await split_service.execute(
            user_id,
            SplitBillRequest(
                action=SplitBillAction.CREATE_GROUP,
                group="Goa Trip",
                participants=["Alice", "Bob"],
            ),
        )

        # 1. Export user data
        exported = await fin_module.export_user_data(str(user_id))
        assert "expenses" in exported
        assert len(exported["expenses"]) == 2
        assert "budgets" in exported
        assert len(exported["budgets"]) == 1
        assert exported["budgets"][0]["category"] == "groceries"
        assert "groups" in exported
        assert len(exported["groups"]) == 1
        assert exported["groups"][0]["name"] == "Goa Trip"

        # 2. Delete user data (GDPR erasure)
        await fin_module.delete_user_data(str(user_id))

        # 3. Verify deletion
        exported_after = await fin_module.export_user_data(str(user_id))
        assert exported_after["expenses"] == []
        assert exported_after["budgets"] == []
        assert exported_after["groups"] == []

        _, list_after, _ = await service.list_expenses(user_id=user_id)
        assert list_after.count == 0

    finally:
        await engine.dispose()
