"""Application service orchestrating category budget workflows (T6.2)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sahayak.core.db.session import UnitOfWork
from sahayak.core.errors import InvalidInputError, NotFoundError
from sahayak.modules.finance.adapters.budgets import SQLAlchemyBudgetRepository
from sahayak.modules.finance.adapters.expenses import SQLAlchemyExpenseRepository
from sahayak.modules.finance.domain.budgets import (
    analyze_budget,
    calculate_month_period,
    format_budget_list_spoken,
    format_budget_removed_spoken,
    format_budget_set_spoken,
    format_budget_status_spoken,
)
from sahayak.modules.finance.domain.categories import normalize_category
from sahayak.modules.finance.domain.money import (
    format_money_display,
    parse_to_minor_units,
)
from sahayak.modules.finance.schemas import (
    BudgetData,
    BudgetRequest,
    BudgetResponseData,
    BudgetStatusData,
)


class BudgetService:
    """Service managing monthly category budgets, status queries, and run rates."""

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

    async def execute(
        self,
        user_id: uuid.UUID,
        request: BudgetRequest,
    ) -> tuple[BudgetResponseData, str]:
        """Dispatch budget action and return response payload and spoken summary."""
        action = request.action.value if hasattr(request.action, "value") else str(request.action)

        if action == "set":
            return await self._handle_set(user_id, request)
        if action == "status":
            return await self._handle_status(user_id, request)
        if action == "list":
            return await self._handle_list(user_id, request)
        if action == "remove":
            return await self._handle_remove(user_id, request)

        raise InvalidInputError(f"Unsupported budget action: {action}")

    async def _handle_set(
        self,
        user_id: uuid.UUID,
        request: BudgetRequest,
    ) -> tuple[BudgetResponseData, str]:
        """Configure or update a monthly category budget."""
        if not request.category or not request.category.strip():
            raise InvalidInputError("Please specify a category for the budget.")

        if request.amount is None:
            raise InvalidInputError("Please specify a monthly budget amount.")

        category = normalize_category(request.category)
        amount_minor = parse_to_minor_units(request.amount)
        if amount_minor <= 0:
            raise InvalidInputError("Budget amount must be greater than zero.")

        currency = (request.currency or "INR").upper().strip()

        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyBudgetRepository(uow.session)
            budget = await repo.upsert_budget(
                user_id=user_id,
                category=category,
                amount_minor=amount_minor,
                currency=currency,
            )
            b_data = BudgetData(
                id=str(budget.id),
                category=budget.category,
                amount_minor=budget.amount_minor,
                currency=budget.currency,
                formatted_amount=format_money_display(budget.amount_minor, budget.currency),
                is_active=budget.is_active,
            )

        spoken = format_budget_set_spoken(category, amount_minor, currency)
        return (
            BudgetResponseData(
                action="set",
                budget=b_data,
                count=1,
            ),
            spoken,
        )

    async def _handle_status(
        self,
        user_id: uuid.UUID,
        request: BudgetRequest,
    ) -> tuple[BudgetResponseData, str]:
        """Check spending status and run-rate analysis for a specific budget."""
        if not request.category or not request.category.strip():
            raise InvalidInputError("Please specify a category to check the budget.")

        category = normalize_category(request.category)

        async with UnitOfWork(self.session_factory) as uow:
            budget_repo = SQLAlchemyBudgetRepository(uow.session)
            expense_repo = SQLAlchemyExpenseRepository(uow.session)

            budget = await budget_repo.get_budget(user_id, category)
            if budget is None:
                raise NotFoundError(
                    f"No active budget found for {category}. "
                    f"Say, set {category} budget to get started."
                )

            period = calculate_month_period(
                reference_utc=self._now(),
                tz_identifier=request.timezone,
            )

            spent_minor = await expense_repo.get_category_spending(
                user_id=user_id,
                category=category,
                currency=budget.currency,
                since=period.start_utc,
                until=period.end_utc,
            )

            analysis = analyze_budget(
                category=category,
                currency=budget.currency,
                budget_minor=budget.amount_minor,
                spent_minor=spent_minor,
                period=period,
            )

        status_data = BudgetStatusData(
            category=analysis.category,
            currency=analysis.currency,
            budget_minor=analysis.budget_minor,
            spent_minor=analysis.spent_minor,
            remaining_minor=analysis.remaining_minor,
            formatted_budget=format_money_display(analysis.budget_minor, analysis.currency),
            formatted_spent=format_money_display(analysis.spent_minor, analysis.currency),
            formatted_remaining=format_money_display(analysis.remaining_minor, analysis.currency),
            is_overspent=analysis.is_overspent,
            percentage_used=analysis.percentage_used,
            projected_overspend_minor=analysis.projected_overspend_minor,
            threshold_crossed=analysis.threshold_crossed,
            days_remaining=analysis.days_remaining,
        )

        spoken = format_budget_status_spoken(analysis)
        return (
            BudgetResponseData(
                action="status",
                status=status_data,
                count=1,
            ),
            spoken,
        )

    async def _handle_list(
        self,
        user_id: uuid.UUID,
        request: BudgetRequest,
    ) -> tuple[BudgetResponseData, str]:
        """List all active category budgets with current spending standings."""
        async with UnitOfWork(self.session_factory) as uow:
            budget_repo = SQLAlchemyBudgetRepository(uow.session)
            expense_repo = SQLAlchemyExpenseRepository(uow.session)

            budgets = await budget_repo.list_budgets(user_id, is_active=True)
            if not budgets:
                spoken = format_budget_list_spoken([])
                return (
                    BudgetResponseData(
                        action="list",
                        budgets=[],
                        count=0,
                    ),
                    spoken,
                )

            period = calculate_month_period(
                reference_utc=self._now(),
                tz_identifier=request.timezone,
            )
            analyses = []

            statuses = []

            for b in budgets:
                spent_minor = await expense_repo.get_category_spending(
                    user_id=user_id,
                    category=b.category,
                    currency=b.currency,
                    since=period.start_utc,
                    until=period.end_utc,
                )
                analysis = analyze_budget(
                    category=b.category,
                    currency=b.currency,
                    budget_minor=b.amount_minor,
                    spent_minor=spent_minor,
                    period=period,
                )
                analyses.append(analysis)
                statuses.append(
                    BudgetStatusData(
                        category=analysis.category,
                        currency=analysis.currency,
                        budget_minor=analysis.budget_minor,
                        spent_minor=analysis.spent_minor,
                        remaining_minor=analysis.remaining_minor,
                        formatted_budget=format_money_display(
                            analysis.budget_minor, analysis.currency
                        ),
                        formatted_spent=format_money_display(
                            analysis.spent_minor, analysis.currency
                        ),
                        formatted_remaining=format_money_display(
                            analysis.remaining_minor, analysis.currency
                        ),
                        is_overspent=analysis.is_overspent,
                        percentage_used=analysis.percentage_used,
                        projected_overspend_minor=analysis.projected_overspend_minor,
                        threshold_crossed=analysis.threshold_crossed,
                        days_remaining=analysis.days_remaining,
                    )
                )

        spoken = format_budget_list_spoken(analyses)
        return (
            BudgetResponseData(
                action="list",
                budgets=statuses,
                count=len(statuses),
            ),
            spoken,
        )

    async def _handle_remove(
        self,
        user_id: uuid.UUID,
        request: BudgetRequest,
    ) -> tuple[BudgetResponseData, str]:
        """Remove or deactivate a category budget."""
        if not request.category or not request.category.strip():
            raise InvalidInputError("Please specify a category to remove the budget.")

        category = normalize_category(request.category)
        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyBudgetRepository(uow.session)
            removed = await repo.remove_budget(user_id, category)
            if not removed:
                raise NotFoundError(f"No active budget found for category '{category}'.")

        spoken = format_budget_removed_spoken(category)
        return (
            BudgetResponseData(
                action="remove",
                count=0,
            ),
            spoken,
        )
