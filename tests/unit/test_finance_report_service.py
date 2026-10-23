"""Unit tests for FinanceReportService and bill tracking (T6.4)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.config import get_settings
from sahayak.core.db.session import UnitOfWork
from sahayak.core.errors import InvalidInputError, NotFoundError
from sahayak.modules.finance.schemas import (
    FinanceReportAction,
    FinanceReportRequest,
)
from sahayak.modules.finance.service.expenses import ExpenseService
from sahayak.modules.finance.service.reports import FinanceReportService
from sahayak.shared.users.models import User


@pytest.mark.asyncio
async def test_finance_report_service_lifecycle() -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    user_id = uuid.uuid4()
    frozen_now = datetime(2026, 3, 20, 10, 0, 0, tzinfo=UTC)
    service = FinanceReportService(
        session_factory=session_factory,
        clock=lambda: frozen_now,
    )
    exp_service = ExpenseService(
        session_factory=session_factory,
        clock=lambda: frozen_now,
    )

    try:
        async with UnitOfWork(session_factory) as uow:
            uow.session.add(User(id=user_id))
            await uow.session.flush()

        # 1. Initially empty summary
        res_empty, spoken_empty = await service.execute(
            user_id,
            FinanceReportRequest(action=FinanceReportAction.SUMMARY),
        )
        assert res_empty.total_spending_minor == 0
        assert "zero expenses" in spoken_empty

        # 2. Add some expenses in March 2026
        await exp_service.add_expense(
            user_id=user_id,
            amount=4500,
            currency="INR",
            category="groceries",
        )
        await exp_service.add_expense(
            user_id=user_id,
            amount=1500,
            currency="INR",
            category="dining",
        )

        # 3. Add a recurring bill: Electricity bill due on 25th
        res_bill, spoken_bill = await service.execute(
            user_id,
            FinanceReportRequest(
                action=FinanceReportAction.ADD_BILL,
                bill_name="Electricity",
                amount=1200,
                due_day=25,
            ),
        )
        assert res_bill.bill is not None
        assert res_bill.bill.name == "Electricity"
        assert res_bill.bill.amount_minor == 120000
        assert "Electricity" in spoken_bill
        bill_id = res_bill.bill.id

        # 4. Monthly summary should now reconcile: total 6000 rupees (600000 minor)
        res_sum, spoken_sum = await service.execute(
            user_id,
            FinanceReportRequest(action=FinanceReportAction.SUMMARY),
        )
        assert res_sum.total_spending_minor == 600000
        assert res_sum.count == 2  # 2 categories
        assert "6000 rupees" in spoken_sum
        assert "groceries" in spoken_sum.lower()
        # Upcoming electricity bill within 7 days (March 20 + 7 = March 27, due is March 25)
        assert len(res_sum.bills) == 1

        # 5. By category report
        res_cat, spoken_cat = await service.execute(
            user_id,
            FinanceReportRequest(action=FinanceReportAction.BY_CATEGORY),
        )
        assert res_cat.count == 2
        assert res_cat.category_breakdown[0].category == "groceries"
        assert res_cat.category_breakdown[0].amount_minor == 450000
        assert "groceries 4500 rupees" in spoken_cat.lower()

        # 6. Bills due check
        res_due, spoken_due = await service.execute(
            user_id,
            FinanceReportRequest(
                action=FinanceReportAction.BILLS_DUE,
                due_days_ahead=7,
            ),
        )
        assert res_due.count == 1
        assert "Electricity 1200 rupees on March 25" in spoken_due

        # 7. Mark bill paid -> roll forward to April 25
        res_paid, spoken_paid = await service.execute(
            user_id,
            FinanceReportRequest(
                action=FinanceReportAction.MARK_BILL_PAID,
                bill_id=bill_id,
            ),
        )
        assert res_paid.bill is not None
        assert res_paid.bill.next_due_date == "2026-04-25"
        assert "Marked Electricity bill of 1200 rupees as paid" in spoken_paid

        # 8. Bills due within next 3 days should now be empty
        res_due_after, spoken_due_after = await service.execute(
            user_id,
            FinanceReportRequest(
                action=FinanceReportAction.BILLS_DUE,
                due_days_ahead=3,
            ),
        )
        assert res_due_after.count == 0
        assert "no upcoming bills" in spoken_due_after

        # 9. Validation error tests
        with pytest.raises(InvalidInputError):
            await service.execute(
                user_id,
                FinanceReportRequest(
                    action=FinanceReportAction.ADD_BILL,
                    bill_name="",
                    amount=100,
                    due_day=5,
                ),
            )

        with pytest.raises(NotFoundError):
            await service.execute(
                user_id,
                FinanceReportRequest(
                    action=FinanceReportAction.MARK_BILL_PAID,
                    bill_id=str(uuid.uuid4()),
                ),
            )

    finally:
        await engine.dispose()
