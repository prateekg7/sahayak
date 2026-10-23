"""Task service managing CRUD, validation, and speech formatting for tasks (T5.1)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sahayak.core.db.session import UnitOfWork
from sahayak.core.errors import InvalidInputError, NotFoundError
from sahayak.modules.productivity.adapters.tasks import SQLAlchemyTaskRepository
from sahayak.modules.productivity.domain.tasks import (
    format_tasks_spoken,
    parse_due_date,
    resolve_user_zone,
)
from sahayak.modules.productivity.schemas import TaskData, TasksResponseData


class TaskService:
    """Service orchestrating task operations with Unit of Work transactions."""

    def __init__(
        self,
        session_factory: Any,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.clock = clock or (lambda: datetime.now(ZoneInfo("UTC")))

    def _now(self) -> datetime:
        return self.clock()

    def _parse_task_id(self, task_id_str: str | None) -> uuid.UUID:
        if not task_id_str:
            raise InvalidInputError("task_id is required for this action")
        try:
            return uuid.UUID(task_id_str)
        except (ValueError, TypeError) as err:
            raise InvalidInputError(f"Invalid task_id '{task_id_str}'") from err

    async def create_task(
        self,
        user_id: uuid.UUID,
        title: str | None,
        due_date_str: str | None = None,
        priority: str = "medium",
        list_name: str = "inbox",
        tags: list[str] | None = None,
        timezone_str: str = "UTC",
    ) -> tuple[str, TasksResponseData, list[str]]:
        if not title or not title.strip():
            raise InvalidInputError("title cannot be empty")

        clean_title = title.strip()
        user_tz = resolve_user_zone(timezone_str)
        due_at = None
        if due_date_str:
            due_at = parse_due_date(due_date_str, self._now(), user_tz)

        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyTaskRepository(uow.session)
            task = await repo.create_task(
                user_id=user_id,
                title=clean_title,
                list_name=list_name,
                priority=priority,
                status="pending",
                due_at=due_at,
                tags=tags or [],
            )
            task_dict = task.to_dict()

        # Format spoken summary
        spoken = f"Added task {clean_title}"
        if list_name and list_name != "inbox":
            spoken += f" to {list_name}"
        if due_at:
            local_due = due_at.astimezone(user_tz)
            spoken += f", due {local_due.strftime('%A, %b %d')}."
        else:
            spoken += "."

        data = TasksResponseData(
            action="create",
            task=TaskData(**task_dict),
            count=1,
        )
        next_actions = ["what's on my list?", "mark it done"]
        return spoken, data, next_actions

    async def list_tasks(
        self,
        user_id: uuid.UUID,
        status: str | None = "pending",
        list_name: str | None = None,
        limit: int = 5,
        timezone_str: str = "UTC",
    ) -> tuple[str, TasksResponseData, list[str]]:
        user_tz = resolve_user_zone(timezone_str)

        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyTaskRepository(uow.session)
            tasks = await repo.list_tasks(
                user_id=user_id,
                status=status,
                list_name=list_name,
                limit=limit,
            )
            tasks_dicts = [t.to_dict() for t in tasks]

        spoken = format_tasks_spoken(tasks_dicts, list_name=list_name, user_tz=user_tz)
        data = TasksResponseData(
            action="list",
            tasks=[TaskData(**d) for d in tasks_dicts],
            count=len(tasks_dicts),
        )
        next_actions = ["add a task", "mark task done"]
        return spoken, data, next_actions

    async def complete_task(
        self,
        user_id: uuid.UUID,
        task_id_str: str | None,
    ) -> tuple[str, TasksResponseData, list[str]]:
        task_id = self._parse_task_id(task_id_str)

        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyTaskRepository(uow.session)
            task = await repo.update_task_status(user_id, task_id, "completed")
            if not task:
                raise NotFoundError(f"Task '{task_id}' not found")
            task_dict = task.to_dict()

        title = task_dict.get("title", "Task")
        spoken = f"Marked {title} as completed."
        data = TasksResponseData(
            action="complete",
            task=TaskData(**task_dict),
            count=1,
        )
        next_actions = ["what's on my list?"]
        return spoken, data, next_actions

    async def reschedule_task(
        self,
        user_id: uuid.UUID,
        task_id_str: str | None,
        due_date_str: str | None,
        timezone_str: str = "UTC",
    ) -> tuple[str, TasksResponseData, list[str]]:
        task_id = self._parse_task_id(task_id_str)
        if not due_date_str:
            raise InvalidInputError("due_date is required for rescheduling")

        user_tz = resolve_user_zone(timezone_str)
        new_due_at = parse_due_date(due_date_str, self._now(), user_tz)
        if not new_due_at:
            raise InvalidInputError("due_date could not be parsed")

        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyTaskRepository(uow.session)
            task = await repo.reschedule_task(user_id, task_id, new_due_at)
            if not task:
                raise NotFoundError(f"Task '{task_id}' not found")
            task_dict = task.to_dict()

        title = task_dict.get("title", "Task")
        local_due = new_due_at.astimezone(user_tz)
        spoken = f"Rescheduled {title} to {local_due.strftime('%A, %b %d')}."
        data = TasksResponseData(
            action="reschedule",
            task=TaskData(**task_dict),
            count=1,
        )
        next_actions = ["what's on my list?"]
        return spoken, data, next_actions

    async def delete_task(
        self,
        user_id: uuid.UUID,
        task_id_str: str | None,
    ) -> tuple[str, TasksResponseData, list[str]]:
        task_id = self._parse_task_id(task_id_str)

        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyTaskRepository(uow.session)
            task = await repo.get_task(user_id, task_id)
            if not task:
                raise NotFoundError(f"Task '{task_id}' not found")
            title = task.title
            task_dict = task.to_dict()
            await repo.delete_task(user_id, task_id)

        spoken = f"Deleted task {title}."
        data = TasksResponseData(
            action="delete",
            task=TaskData(**task_dict),
            count=1,
        )
        next_actions = ["what's on my list?"]
        return spoken, data, next_actions
