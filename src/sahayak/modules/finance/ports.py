"""Port interfaces for the finance module (T6.1)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Protocol

from sahayak.modules.finance.models import Expense


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
