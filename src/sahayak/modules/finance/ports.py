"""Port interfaces for the finance module (T6.1)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Protocol

from sahayak.modules.finance.models import (
    Bill,
    Budget,
    Expense,
    Group,
    GroupMember,
    Settlement,
    SharedExpense,
)


class ExpenseRepositoryPort(Protocol):
    """Repository port interface for personal expenses."""

    async def create_expense(
        self,
        user_id: uuid.UUID,
        amount_minor: int,
        currency: str,
        category: str,
        note: str | None = None,
        occurred_at: datetime | None = None,
    ) -> Expense:
        """Create and persist a new expense."""
        ...

    async def get_expense(self, user_id: uuid.UUID, expense_id: uuid.UUID) -> Expense | None:
        """Retrieve an expense by ID, scoped by user_id."""
        ...

    async def get_latest_expense(self, user_id: uuid.UUID) -> Expense | None:
        """Retrieve the most recent active expense for a user."""
        ...

    async def list_expenses(
        self,
        user_id: uuid.UUID,
        category: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 10,
    ) -> list[Expense]:
        """List active expenses for a user, ordered by occurred_at DESC."""
        ...

    async def soft_delete_expense(self, user_id: uuid.UUID, expense_id: uuid.UUID) -> bool:
        """Mark an expense as deleted (soft delete for undo and auditability)."""
        ...

    async def undo_last_expense(self, user_id: uuid.UUID) -> Expense | None:
        """Undo the most recent active expense by marking it deleted."""
        ...

    async def get_total_spending(
        self,
        user_id: uuid.UUID,
        currency: str,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> int:
        """Sum total active spending in integer minor units for a given period."""
        ...

    async def get_category_spending(
        self,
        user_id: uuid.UUID,
        category: str,
        currency: str,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> int:
        """Sum active spending for a category in integer minor units for a given period."""
        ...

    async def get_spending_by_category(
        self,
        user_id: uuid.UUID,
        currency: str,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> dict[str, int]:
        """Return a mapping of category -> total minor units spent in the given period."""
        ...


class BudgetRepositoryPort(Protocol):
    """Repository port interface for monthly category budgets (T6.2)."""

    async def upsert_budget(
        self,
        user_id: uuid.UUID,
        category: str,
        amount_minor: int,
        currency: str = "INR",
    ) -> Budget:
        """Create or update an active budget for a user and category."""
        ...

    async def get_budget(self, user_id: uuid.UUID, category: str) -> Budget | None:
        """Retrieve an active budget for a user and category."""
        ...

    async def list_budgets(
        self,
        user_id: uuid.UUID,
        is_active: bool = True,
    ) -> list[Budget]:
        """List category budgets for a user."""
        ...

    async def remove_budget(self, user_id: uuid.UUID, category: str) -> bool:
        """Deactivate or remove a category budget."""
        ...


class SplitBillRepositoryPort(Protocol):
    """Repository port interface for bill splitting and debt settlements (T6.3)."""

    async def create_group(
        self,
        user_id: uuid.UUID,
        name: str,
        currency: str = "INR",
        members: list[str] | None = None,
    ) -> Group:
        """Create a new group and add initial members."""
        ...

    async def get_group_by_name(self, user_id: uuid.UUID, name: str) -> Group | None:
        """Find a group by name for a user."""
        ...

    async def get_group(self, user_id: uuid.UUID, group_id: uuid.UUID) -> Group | None:
        """Find a group by ID for a user."""
        ...

    async def list_groups(self, user_id: uuid.UUID) -> list[Group]:
        """List all groups owned by a user."""
        ...

    async def get_group_members(self, group_id: uuid.UUID) -> list[GroupMember]:
        """Get all named participants in a group."""
        ...

    async def add_group_members(
        self, group_id: uuid.UUID, member_names: list[str]
    ) -> list[GroupMember]:
        """Add new members to an existing group if not already present."""
        ...

    async def create_shared_expense(
        self,
        group_id: uuid.UUID,
        payer_name: str,
        total_minor: int,
        description: str,
        split_data: dict[str, int],
    ) -> SharedExpense:
        """Persist a shared expense with itemized split shares."""
        ...

    async def list_shared_expenses(self, group_id: uuid.UUID) -> list[SharedExpense]:
        """List all shared expenses recorded for a group."""
        ...

    async def create_settlement(
        self,
        group_id: uuid.UUID,
        from_name: str,
        to_name: str,
        amount_minor: int,
    ) -> Settlement:
        """Record a debt settlement between two members."""
        ...

    async def list_settlements(self, group_id: uuid.UUID) -> list[Settlement]:
        """List all recorded settlements for a group."""
        ...


class BillRepositoryPort(Protocol):
    """Repository port interface for recurring bills and EMI due dates (T6.4)."""

    async def create_bill(
        self,
        user_id: uuid.UUID,
        name: str,
        amount_minor: int,
        due_day: int,
        next_due_date: date,
        currency: str = "INR",
        frequency: str = "monthly",
    ) -> Bill:
        """Create a new recurring bill record."""
        ...

    async def get_bill(self, user_id: uuid.UUID, bill_id: uuid.UUID) -> Bill | None:
        """Get a bill by ID scoped by user_id."""
        ...

    async def list_bills(
        self,
        user_id: uuid.UUID,
        is_active: bool = True,
        due_before: date | None = None,
    ) -> list[Bill]:
        """List bills for a user, optionally filtered by due_before date."""
        ...

    async def mark_bill_paid(
        self,
        user_id: uuid.UUID,
        bill_id: uuid.UUID,
        next_due_date: date,
    ) -> Bill | None:
        """Mark bill paid for the current cycle and roll forward next_due_date."""
        ...

    async def deactivate_bill(self, user_id: uuid.UUID, bill_id: uuid.UUID) -> bool:
        """Deactivate a recurring bill."""
        ...
