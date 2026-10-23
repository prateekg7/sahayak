"""Expense logging and reporting service with zero floating-point operations (T6.1)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sahayak.core.db.session import UnitOfWork
from sahayak.core.errors import InvalidInputError, NotFoundError
from sahayak.modules.finance.adapters.expenses import SQLAlchemyExpenseRepository
from sahayak.modules.finance.domain.categories import normalize_category
from sahayak.modules.finance.domain.money import (
    format_money_display,
    format_money_spoken,
    parse_to_minor_units,
)
from sahayak.modules.finance.schemas import ExpenseData, ExpenseResponseData


class ExpenseService:
    """Service managing personal expenses, undo operations, and list summaries."""

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

    def _parse_id(self, raw_id: str | None) -> uuid.UUID:
        if not raw_id:
            raise InvalidInputError("expense_id is required for this action")
        try:
            return uuid.UUID(raw_id)
        except (ValueError, TypeError) as err:
            raise InvalidInputError(f"Invalid expense_id '{raw_id}'") from err

    async def add_expense(
        self,
        user_id: uuid.UUID,
        amount: str | int | None,
        currency: str = "INR",
        category: str | None = None,
        note: str | None = None,
    ) -> tuple[str, ExpenseResponseData, list[str]]:
        """Log a new expense entry in minor units."""
        curr = currency.upper().strip()
        amount_minor = parse_to_minor_units(amount, currency=curr)
        normalized_cat = normalize_category(category, note)
        now = self._now()

        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyExpenseRepository(uow.session)
            expense = await repo.create_expense(
                user_id=user_id,
                amount_minor=amount_minor,
                currency=curr,
                category=normalized_cat,
                note=note,
                occurred_at=now,
            )
            expense_dict = expense.to_dict()

        spoken_amt = format_money_spoken(amount_minor, curr)
        disp_amt = format_money_display(amount_minor, curr)
        expense_data = ExpenseData(
            id=expense_dict["id"],
            user_id=expense_dict["user_id"],
            amount_minor=amount_minor,
            currency=curr,
            category=normalized_cat,
            note=note,
            occurred_at=expense_dict["occurred_at"],
            formatted_amount=disp_amt,
        )

        spoken = f"Added {spoken_amt} for {normalized_cat}."
        data = ExpenseResponseData(
            action="add",
            expense=expense_data,
            total_amount_minor=amount_minor,
            formatted_total=disp_amt,
            currency=curr,
            count=1,
        )
        next_actions = ["what did I spend today", "undo last expense"]
        return spoken, data, next_actions

    async def list_expenses(
        self,
        user_id: uuid.UUID,
        category: str | None = None,
        limit: int = 5,
        currency: str = "INR",
    ) -> tuple[str, ExpenseResponseData, list[str]]:
        """List recent active expenses and calculate total spending."""
        curr = currency.upper().strip()

        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyExpenseRepository(uow.session)
            expenses = await repo.list_expenses(
                user_id=user_id,
                category=category,
                limit=limit,
            )
            expenses_dicts = [e.to_dict() for e in expenses]

        if not expenses_dicts:
            cat_part = f" for {category}" if category else ""
            spoken = f"You have not logged any expenses{cat_part} yet."
            data = ExpenseResponseData(
                action="list",
                currency=curr,
                count=0,
            )
            return spoken, data, ["add 200 rupees for groceries"]

        total_minor = sum(d["amount_minor"] for d in expenses_dicts)
        items_data = [
            ExpenseData(
                id=d["id"],
                user_id=d["user_id"],
                amount_minor=d["amount_minor"],
                currency=d["currency"],
                category=d["category"],
                note=d["note"],
                occurred_at=d["occurred_at"],
                formatted_amount=format_money_display(d["amount_minor"], d["currency"]),
            )
            for d in expenses_dicts
        ]

        spoken_total = format_money_spoken(total_minor, curr)
        disp_total = format_money_display(total_minor, curr)

        if len(items_data) == 1:
            spoken = f"You have 1 recent expense totaling {spoken_total}."
        else:
            spoken = f"You have {len(items_data)} recent expenses totaling {spoken_total}."

        data = ExpenseResponseData(
            action="list",
            expenses=items_data,
            total_amount_minor=total_minor,
            formatted_total=disp_total,
            currency=curr,
            count=len(items_data),
        )
        next_actions = ["undo last expense", "add an expense"]
        return spoken, data, next_actions

    async def undo_last_expense(
        self,
        user_id: uuid.UUID,
    ) -> tuple[str, ExpenseResponseData, list[str]]:
        """Undo the most recently logged active expense."""
        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyExpenseRepository(uow.session)
            undone = await repo.undo_last_expense(user_id)
            if undone is None:
                raise NotFoundError("You do not have any recent expenses to undo.")
            d = undone.to_dict()

        spoken_amt = format_money_spoken(d["amount_minor"], d["currency"])
        disp_amt = format_money_display(d["amount_minor"], d["currency"])
        expense_data = ExpenseData(
            id=d["id"],
            user_id=d["user_id"],
            amount_minor=d["amount_minor"],
            currency=d["currency"],
            category=d["category"],
            note=d["note"],
            occurred_at=d["occurred_at"],
            formatted_amount=disp_amt,
        )

        spoken = f"Undid your last expense of {spoken_amt} for {d['category']}."
        data = ExpenseResponseData(
            action="undo_last",
            expense=expense_data,
            count=1,
            currency=d["currency"],
        )
        next_actions = ["add an expense", "list my expenses"]
        return spoken, data, next_actions

    async def delete_expense(
        self,
        user_id: uuid.UUID,
        expense_id_str: str | None,
    ) -> tuple[str, ExpenseResponseData, list[str]]:
        """Soft delete a specific expense by ID."""
        expense_id = self._parse_id(expense_id_str)

        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyExpenseRepository(uow.session)
            deleted = await repo.soft_delete_expense(user_id=user_id, expense_id=expense_id)
            if not deleted:
                raise NotFoundError(f"Expense '{expense_id}' not found.")

        spoken = "Deleted the expense."
        data = ExpenseResponseData(
            action="delete",
            count=1,
        )
        next_actions = ["list my expenses"]
        return spoken, data, next_actions
