"""Application service orchestrating financial reports and recurring bill tracking (T6.4)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sahayak.core.db.session import UnitOfWork
from sahayak.core.errors import InvalidInputError, NotFoundError
from sahayak.modules.finance.adapters.bills import SQLAlchemyBillRepository
from sahayak.modules.finance.adapters.expenses import SQLAlchemyExpenseRepository
from sahayak.modules.finance.domain.money import (
    format_money_display,
    parse_to_minor_units,
)
from sahayak.modules.finance.domain.reports import (
    calculate_initial_due_date,
    calculate_report_period,
    compare_spending,
    compute_next_due_date,
    format_add_bill_spoken,
    format_bills_due_spoken,
    format_by_category_spoken,
    format_mark_paid_spoken,
    format_summary_spoken,
)
from sahayak.modules.finance.models import Bill
from sahayak.modules.finance.schemas import (
    BillData,
    CategorySpendingData,
    FinanceReportRequest,
    FinanceReportResponseData,
)


class FinanceReportService:
    """Service providing financial reports, category analysis, and bill tracking."""

    def __init__(
        self,
        session_factory: Any,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.clock = clock or (lambda: datetime.now(UTC))

    def _now(self) -> datetime:
        dt = self.clock()
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)

    def _bill_to_data(self, bill: Bill) -> BillData:
        return BillData(
            id=str(bill.id),
            name=bill.name,
            amount_minor=bill.amount_minor,
            formatted_amount=format_money_display(bill.amount_minor, bill.currency),
            currency=bill.currency,
            frequency=bill.frequency,
            due_day=bill.due_day,
            next_due_date=bill.next_due_date.isoformat(),
            is_paid=bill.is_paid,
            is_active=bill.is_active,
        )

    async def execute(
        self,
        user_id: uuid.UUID,
        request: FinanceReportRequest,
    ) -> tuple[FinanceReportResponseData, str]:
        """Dispatch finance report action and return response payload and spoken summary."""
        action = request.action.value if hasattr(request.action, "value") else str(request.action)

        if action == "summary":
            return await self._handle_summary(user_id, request)
        if action == "by_category":
            return await self._handle_by_category(user_id, request)
        if action == "bills_due":
            return await self._handle_bills_due(user_id, request)
        if action == "add_bill":
            return await self._handle_add_bill(user_id, request)
        if action == "mark_bill_paid":
            return await self._handle_mark_bill_paid(user_id, request)

        raise InvalidInputError(
            f"Unknown action: {action}. Expected 'summary', 'by_category', 'bills_due', "
            "'add_bill', or 'mark_bill_paid'."
        )

    async def _handle_summary(
        self,
        user_id: uuid.UUID,
        request: FinanceReportRequest,
    ) -> tuple[FinanceReportResponseData, str]:
        now = self._now()
        curr_start, curr_end, prev_start, prev_end = calculate_report_period(request.period, now)
        currency = request.currency.upper().strip()

        async with UnitOfWork(self.session_factory) as uow:
            exp_repo = SQLAlchemyExpenseRepository(uow.session)
            bill_repo = SQLAlchemyBillRepository(uow.session)

            curr_total = await exp_repo.get_total_spending(
                user_id=user_id,
                currency=currency,
                since=curr_start,
                until=curr_end,
            )
            prev_total = await exp_repo.get_total_spending(
                user_id=user_id,
                currency=currency,
                since=prev_start,
                until=prev_end,
            )
            cat_spending = await exp_repo.get_spending_by_category(
                user_id=user_id,
                currency=currency,
                since=curr_start,
                until=curr_end,
            )

            # Check upcoming bills in next 7 days
            upcoming_cutoff = now.date() + timedelta(days=7)
            bills = await bill_repo.list_bills(
                user_id=user_id,
                is_active=True,
                due_before=upcoming_cutoff,
            )

        diff_minor, pct = compare_spending(curr_total, prev_total)

        top_cat: str | None = None
        top_minor = 0
        cat_breakdown: list[CategorySpendingData] = []
        for cat, minor in sorted(cat_spending.items(), key=lambda x: x[1], reverse=True):
            if minor > top_minor:
                top_minor = minor
                top_cat = cat
            pct_share = round((minor / curr_total) * 100, 1) if curr_total > 0 else 0.0
            cat_breakdown.append(
                CategorySpendingData(
                    category=cat,
                    amount_minor=minor,
                    formatted_amount=format_money_display(minor, currency),
                    percentage=pct_share,
                )
            )

        upcoming_minor = sum(b.amount_minor for b in bills if b.currency == currency)

        spoken = format_summary_spoken(
            period=request.period,
            current_minor=curr_total,
            previous_minor=prev_total,
            diff_minor=diff_minor,
            pct=pct,
            currency=currency,
            categories_count=len(cat_breakdown),
            top_category=top_cat,
            top_cat_minor=top_minor,
            upcoming_bills_count=len(bills),
            upcoming_bills_minor=upcoming_minor,
        )

        data = FinanceReportResponseData(
            action="summary",
            period=request.period,
            currency=currency,
            total_spending_minor=curr_total,
            formatted_total_spending=format_money_display(curr_total, currency),
            previous_period_spending_minor=prev_total,
            formatted_previous_spending=format_money_display(prev_total, currency),
            diff_minor=diff_minor,
            percentage_change=pct,
            category_breakdown=cat_breakdown,
            bills=[self._bill_to_data(b) for b in bills],
            count=len(cat_breakdown),
        )
        return data, spoken

    async def _handle_by_category(
        self,
        user_id: uuid.UUID,
        request: FinanceReportRequest,
    ) -> tuple[FinanceReportResponseData, str]:
        now = self._now()
        curr_start, curr_end, _, _ = calculate_report_period(request.period, now)
        currency = request.currency.upper().strip()

        async with UnitOfWork(self.session_factory) as uow:
            exp_repo = SQLAlchemyExpenseRepository(uow.session)
            curr_total = await exp_repo.get_total_spending(
                user_id=user_id,
                currency=currency,
                since=curr_start,
                until=curr_end,
            )
            cat_spending = await exp_repo.get_spending_by_category(
                user_id=user_id,
                currency=currency,
                since=curr_start,
                until=curr_end,
            )

        cat_breakdown: list[CategorySpendingData] = []
        tuple_list: list[tuple[str, int, float]] = []

        for cat, minor in sorted(cat_spending.items(), key=lambda x: x[1], reverse=True):
            pct_share = round((minor / curr_total) * 100, 1) if curr_total > 0 else 0.0
            cat_breakdown.append(
                CategorySpendingData(
                    category=cat,
                    amount_minor=minor,
                    formatted_amount=format_money_display(minor, currency),
                    percentage=pct_share,
                )
            )
            tuple_list.append((cat, minor, pct_share))

        spoken = format_by_category_spoken(request.period, tuple_list, currency)

        data = FinanceReportResponseData(
            action="by_category",
            period=request.period,
            currency=currency,
            total_spending_minor=curr_total,
            formatted_total_spending=format_money_display(curr_total, currency),
            category_breakdown=cat_breakdown,
            count=len(cat_breakdown),
        )
        return data, spoken

    async def _handle_bills_due(
        self,
        user_id: uuid.UUID,
        request: FinanceReportRequest,
    ) -> tuple[FinanceReportResponseData, str]:
        now = self._now()
        due_cutoff = now.date() + timedelta(days=request.due_days_ahead)
        currency = request.currency.upper().strip()

        async with UnitOfWork(self.session_factory) as uow:
            bill_repo = SQLAlchemyBillRepository(uow.session)
            bills = await bill_repo.list_bills(
                user_id=user_id,
                is_active=True,
                due_before=due_cutoff,
            )

        spoken = format_bills_due_spoken(bills, currency, request.due_days_ahead)
        bill_data_list = [self._bill_to_data(b) for b in bills]

        total_due = sum(b.amount_minor for b in bills if b.currency == currency)

        data = FinanceReportResponseData(
            action="bills_due",
            period=request.period,
            currency=currency,
            total_spending_minor=total_due,
            formatted_total_spending=format_money_display(total_due, currency),
            bills=bill_data_list,
            count=len(bill_data_list),
        )
        return data, spoken

    async def _handle_add_bill(
        self,
        user_id: uuid.UUID,
        request: FinanceReportRequest,
    ) -> tuple[FinanceReportResponseData, str]:
        if not request.bill_name or not request.bill_name.strip():
            raise InvalidInputError("bill_name is required when adding a recurring bill.")
        if request.amount is None:
            raise InvalidInputError("amount is required when adding a recurring bill.")
        if request.due_day is None or not (1 <= request.due_day <= 31):
            raise InvalidInputError(
                "due_day between 1 and 31 is required when adding a recurring bill."
            )

        amount_minor = parse_to_minor_units(request.amount, request.currency)
        now = self._now()
        initial_due = calculate_initial_due_date(request.due_day, request.frequency, now.date())
        currency = request.currency.upper().strip()

        async with UnitOfWork(self.session_factory) as uow:
            bill_repo = SQLAlchemyBillRepository(uow.session)
            bill = await bill_repo.create_bill(
                user_id=user_id,
                name=request.bill_name.strip(),
                amount_minor=amount_minor,
                due_day=request.due_day,
                next_due_date=initial_due,
                currency=currency,
                frequency=request.frequency,
            )

        spoken = format_add_bill_spoken(
            name=bill.name,
            amount_minor=bill.amount_minor,
            currency=bill.currency,
            due_day=bill.due_day,
            next_due=bill.next_due_date,
        )

        bill_data = self._bill_to_data(bill)
        data = FinanceReportResponseData(
            action="add_bill",
            period=request.period,
            currency=currency,
            bill=bill_data,
            bills=[bill_data],
            count=1,
        )
        return data, spoken

    async def _handle_mark_bill_paid(
        self,
        user_id: uuid.UUID,
        request: FinanceReportRequest,
    ) -> tuple[FinanceReportResponseData, str]:
        if not request.bill_id:
            raise InvalidInputError("bill_id is required to mark a bill paid.")

        try:
            bid = uuid.UUID(request.bill_id)
        except ValueError as err:
            raise InvalidInputError(f"Invalid bill_id UUID: {request.bill_id}") from err

        async with UnitOfWork(self.session_factory) as uow:
            bill_repo = SQLAlchemyBillRepository(uow.session)
            bill = await bill_repo.get_bill(user_id, bid)
            if bill is None or not bill.is_active:
                raise NotFoundError(f"Active bill with id '{request.bill_id}' not found.")

            next_due = compute_next_due_date(bill.due_day, bill.frequency, bill.next_due_date)
            updated_bill = await bill_repo.mark_bill_paid(user_id, bid, next_due)
            if updated_bill is None:
                raise NotFoundError(f"Bill '{request.bill_id}' could not be updated.")

        spoken = format_mark_paid_spoken(
            name=updated_bill.name,
            amount_minor=updated_bill.amount_minor,
            currency=updated_bill.currency,
            next_due=updated_bill.next_due_date,
        )

        bill_data = self._bill_to_data(updated_bill)
        data = FinanceReportResponseData(
            action="mark_bill_paid",
            period=request.period,
            currency=updated_bill.currency,
            bill=bill_data,
            bills=[bill_data],
            count=1,
        )
        return data, spoken
