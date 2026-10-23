"""Port interfaces for the productivity module (T5.1)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Protocol

from sahayak.modules.productivity.models import Task


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
