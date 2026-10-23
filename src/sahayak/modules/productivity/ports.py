"""Port interfaces for the productivity module (T5.1)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Protocol

from sahayak.modules.productivity.models import Habit, HabitLog, Task


class TaskRepositoryPort(Protocol):
    """Repository port interface for task persistence."""

    async def create_task(
        self,
        user_id: uuid.UUID,
        title: str,
        list_name: str = "inbox",
        priority: str = "medium",
        status: str = "pending",
        due_at: datetime | None = None,
        tags: list[str] | None = None,
    ) -> Task:
        """Create and persist a new task."""
        ...

    async def get_task(self, user_id: uuid.UUID, task_id: uuid.UUID) -> Task | None:
        """Retrieve task by ID, scoped by user_id."""
        ...

    async def list_tasks(
        self,
        user_id: uuid.UUID,
        status: str | None = None,
        list_name: str | None = None,
        limit: int = 5,
    ) -> list[Task]:
        """List tasks scoped by user_id with optional status and list filters."""
        ...

    async def update_task_status(
        self,
        user_id: uuid.UUID,
        task_id: uuid.UUID,
        status: str,
    ) -> Task | None:
        """Update task status (e.g. pending -> completed), setting completed_at if completed."""
        ...

    async def reschedule_task(
        self,
        user_id: uuid.UUID,
        task_id: uuid.UUID,
        due_at: datetime,
    ) -> Task | None:
        """Update task due date, scoped by user_id."""
        ...

    async def delete_task(self, user_id: uuid.UUID, task_id: uuid.UUID) -> bool:
        """Delete task by ID, scoped by user_id."""
        ...

    async def count_pending_tasks(
        self,
        user_id: uuid.UUID,
        list_name: str | None = None,
    ) -> int:
        """Count pending tasks for a user."""
        ...

    async def get_due_today_tasks(
        self,
        user_id: uuid.UUID,
        start_of_day: datetime,
        end_of_day: datetime,
    ) -> list[Task]:
        """Get tasks due on a specific local calendar day."""
        ...


class HabitRepositoryPort(Protocol):
    """Repository port interface for habit tracking and completion logging."""

    async def create_habit(
        self,
        user_id: uuid.UUID,
        name: str,
        target_frequency: str = "daily",
    ) -> Habit:
        """Create and persist a new habit."""
        ...

    async def get_habit(self, user_id: uuid.UUID, habit_id: uuid.UUID) -> Habit | None:
        """Retrieve habit by ID, scoped by user_id."""
        ...

    async def get_habit_by_name(self, user_id: uuid.UUID, name: str) -> Habit | None:
        """Retrieve habit by case-insensitive name, scoped by user_id."""
        ...

    async def list_habits(
        self,
        user_id: uuid.UUID,
        include_archived: bool = False,
    ) -> list[Habit]:
        """List all habits owned by a user."""
        ...

    async def log_habit(
        self,
        user_id: uuid.UUID,
        habit_id: uuid.UUID,
        logged_date: date,
        notes: str | None = None,
    ) -> tuple[HabitLog, bool]:
        """Log a habit completion on a specific calendar date (idempotent on habit_id + date)."""
        ...

    async def get_habit_logs(
        self,
        habit_id: uuid.UUID,
        limit: int = 365,
    ) -> list[HabitLog]:
        """Get recent logs for a habit ordered by date descending."""
        ...

    async def update_habit_streak(
        self,
        habit_id: uuid.UUID,
        streak_current: int,
        streak_longest: int,
        last_logged_date: date,
    ) -> Habit | None:
        """Update habit's streak metrics and last completion date."""
        ...

    async def archive_habit(
        self,
        user_id: uuid.UUID,
        habit_id: uuid.UUID,
    ) -> Habit | None:
        """Archive a habit, scoped by user_id."""
        ...
