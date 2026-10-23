"""Finance module definition satisfying the Module protocol (T6.1)."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select

from sahayak.core.db.session import UnitOfWork
from sahayak.core.module import Deps, HealthStatus
from sahayak.modules.finance.models import Expense


class FinanceModule:
    """Finance module providing personal expense logging, budgets, and bill splitting."""

    def __init__(self) -> None:
        self._deps: Deps | None = None
        self._api: Any = None

    @property
    def name(self) -> str:
        return "finance"

    @property
    def version(self) -> str:
        return "0.1.0"

    @property
    def api(self) -> Any:
        """Cross-module API instance for querying spending statistics."""
        if self._api is None:
            if self._deps is None or self._deps.session_factory is None:
                raise RuntimeError("FinanceModule has not been initialized with dependencies")
            from sahayak.modules.finance.api import FinanceAPI

            clock_fn = getattr(self._deps, "clock", None)
            self._api = FinanceAPI(
                session_factory=self._deps.session_factory,
                clock=clock_fn,
            )
        return self._api

    def register_tools(self, mcp: Any, deps: Deps) -> None:
        """Register MCP tools provided by the finance module."""
        self._deps = deps
        if deps.session_factory is not None:
            from sahayak.modules.finance.service.expenses import ExpenseService
            from sahayak.modules.finance.tools.expense_log import set_expense_service

            clock_fn = getattr(deps, "clock", None)
            expense_service = ExpenseService(
                session_factory=deps.session_factory,
                clock=clock_fn,
            )
            set_expense_service(expense_service)

        from sahayak.modules.finance.tools.expense_log import (
            EXPENSE_LOG_DESCRIPTION,
            expense_log,
        )

        tool_decorator = getattr(mcp, "tool", None)
        if callable(tool_decorator):
            tool_decorator(name="expense_log", description=EXPENSE_LOG_DESCRIPTION)(expense_log)
        elif hasattr(mcp, "add_tool"):
            mcp.add_tool(expense_log, name="expense_log", description=EXPENSE_LOG_DESCRIPTION)

    def register_jobs(self, worker: Any) -> None:
        """Register background jobs for finance module."""
        pass

    def migrations_path(self) -> str | None:
        return str(Path(__file__).parent / "migrations")

    def health(self) -> HealthStatus:
        if self._deps is not None and self._deps.session_factory is None:
            return HealthStatus(healthy=False, detail="PostgreSQL session factory missing")
        return HealthStatus(healthy=True, detail="Finance module is operational")

    def on_event(self, event: Any) -> None:
        """Dispatched domain events hook."""
        pass

    async def export_user_data(self, user_id: str) -> dict[str, Any]:
        """GDPR Right to Access: export all personal expenses owned by user_id."""
        if self._deps is None or self._deps.session_factory is None:
            return {}

        uid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
        async with UnitOfWork(self._deps.session_factory) as uow:
            res = await uow.session.execute(select(Expense).where(Expense.user_id == uid))
            expenses = res.scalars().all()
            return {"expenses": [e.to_dict() for e in expenses]}

    async def delete_user_data(self, user_id: str) -> None:
        """GDPR Right to Erasure: permanently delete all expenses owned by user_id."""
        if self._deps is None or self._deps.session_factory is None:
            return

        uid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
        async with UnitOfWork(self._deps.session_factory) as uow:
            await uow.session.execute(delete(Expense).where(Expense.user_id == uid))


module = FinanceModule()
