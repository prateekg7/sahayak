"""Public cross-module API contract and implementation for productivity (T5.1)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime, time, timedelta
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from sahayak.core.db.session import UnitOfWork
from sahayak.modules.productivity.adapters.habits import SQLAlchemyHabitRepository
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

    async def get_weekly_habit_stats(
        self, user_id: uuid.UUID, timezone_str: str = "UTC"
    ) -> dict[str, Any]:
        """Return weekly habit completion statistics over the past 7 days."""
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

    async def get_weekly_habit_stats(
        self, user_id: uuid.UUID, timezone_str: str = "UTC"
    ) -> dict[str, Any]:
        user_tz = resolve_user_zone(timezone_str)
        now_local = self.clock().astimezone(user_tz)
        seven_days_ago = now_local.date() - timedelta(days=7)

        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyHabitRepository(uow.session)
            habits = await repo.list_habits(user_id, include_archived=False)
            if not habits:
                return {"active_count": 0, "completions_count": 0, "top_habit": None}

            total_completions = 0
            best_habit_name = None
            max_habit_logs = -1

            for h in habits:
                logs = await repo.get_habit_logs(h.id, limit=30)
                recent_logs = [entry for entry in logs if entry.logged_date >= seven_days_ago]
                count = len(recent_logs)
                total_completions += count
                if count > max_habit_logs:
                    max_habit_logs = count
                    best_habit_name = h.name

            return {
                "active_count": len(habits),
                "completions_count": total_completions,
                "top_habit": best_habit_name if total_completions > 0 else None,
            }
