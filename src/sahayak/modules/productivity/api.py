"""Public cross-module API contract and implementation for productivity (T5.1)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime, time
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from sahayak.core.db.session import UnitOfWork
from sahayak.modules.productivity.adapters.tasks import SQLAlchemyTaskRepository
from sahayak.modules.productivity.domain.tasks import resolve_user_zone


class ProductivityModuleAPI(Protocol):
    """Public protocol exposed by Productivity module for cross-module interactions."""

    async def get_pending_tasks_count(self, user_id: uuid.UUID) -> int:
        """Return the total number of pending tasks for a user."""
        ...

    async def get_due_today_tasks(
        self, user_id: uuid.UUID, timezone_str: str = "UTC"
    ) -> list[dict[str, Any]]:
        """Return tasks due on today's calendar date in user's timezone."""
        ...


class ProductivityAPI(ProductivityModuleAPI):
    """Implementation of the cross-module Productivity API."""

    def __init__(
        self,
        session_factory: Any,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.clock = clock or (lambda: datetime.now(ZoneInfo("UTC")))

    async def get_pending_tasks_count(self, user_id: uuid.UUID) -> int:
        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyTaskRepository(uow.session)
            return await repo.count_pending_tasks(user_id)

    async def get_due_today_tasks(
        self, user_id: uuid.UUID, timezone_str: str = "UTC"
    ) -> list[dict[str, Any]]:
        user_tz = resolve_user_zone(timezone_str)
        now_local = self.clock().astimezone(user_tz)
        today = now_local.date()

        start_of_day = datetime.combine(today, time.min, tzinfo=user_tz).astimezone(ZoneInfo("UTC"))
        end_of_day = datetime.combine(today, time.max, tzinfo=user_tz).astimezone(ZoneInfo("UTC"))

        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyTaskRepository(uow.session)
            tasks = await repo.get_due_today_tasks(user_id, start_of_day, end_of_day)
            return [t.to_dict() for t in tasks]
