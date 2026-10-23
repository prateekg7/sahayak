"""SQLAlchemy repository implementation for productivity tasks (T5.1)."""

from __future__ import annotations

import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sahayak.modules.productivity.models import Task
from sahayak.modules.productivity.ports import TaskRepositoryPort


class SQLAlchemyTaskRepository(TaskRepositoryPort):
    """PostgreSQL repository for productivity tasks."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

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
        task = Task(
            id=uuid.uuid4(),
            user_id=user_id,
            title=title.strip(),
            list_name=list_name.strip().lower(),
            priority=priority.strip().lower(),
            status=status.strip().lower(),
            due_at=due_at,
            tags=tags or [],
        )
        self.session.add(task)
        await self.session.flush()
        return task

    async def get_task(self, user_id: uuid.UUID, task_id: uuid.UUID) -> Task | None:
        query = select(Task).where(Task.id == task_id, Task.user_id == user_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_tasks(
        self,
        user_id: uuid.UUID,
        status: str | None = None,
        list_name: str | None = None,
        limit: int = 5,
    ) -> list[Task]:
        query = select(Task).where(Task.user_id == user_id)
        if status:
            query = query.where(Task.status == status.strip().lower())
        if list_name:
            query = query.where(Task.list_name == list_name.strip().lower())

        # Order by nulls last on due_at, then priority, then created_at desc
        query = query.order_by(Task.due_at.asc().nulls_last(), Task.created_at.desc()).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update_task_status(
        self,
        user_id: uuid.UUID,
        task_id: uuid.UUID,
        status: str,
    ) -> Task | None:
        task = await self.get_task(user_id, task_id)
        if not task:
            return None

        clean_status = status.strip().lower()
        task.status = clean_status
        if clean_status == "completed":
            task.completed_at = datetime.now(ZoneInfo("UTC"))
        else:
            task.completed_at = None

        await self.session.flush()
        return task

    async def reschedule_task(
        self,
        user_id: uuid.UUID,
        task_id: uuid.UUID,
        due_at: datetime,
    ) -> Task | None:
        task = await self.get_task(user_id, task_id)
        if not task:
            return None

        task.due_at = due_at
        await self.session.flush()
        return task

    async def delete_task(self, user_id: uuid.UUID, task_id: uuid.UUID) -> bool:
        task = await self.get_task(user_id, task_id)
        if not task:
            return False

        await self.session.delete(task)
        await self.session.flush()
        return True

    async def count_pending_tasks(
        self,
        user_id: uuid.UUID,
        list_name: str | None = None,
    ) -> int:
        query = select(func.count(Task.id)).where(Task.user_id == user_id, Task.status == "pending")
        if list_name:
            query = query.where(Task.list_name == list_name.strip().lower())
        result = await self.session.execute(query)
        count = result.scalar()
        return int(count or 0)

    async def get_due_today_tasks(
        self,
        user_id: uuid.UUID,
        start_of_day: datetime,
        end_of_day: datetime,
    ) -> list[Task]:
        query = (
            select(Task)
            .where(
                Task.user_id == user_id,
                Task.status == "pending",
                Task.due_at >= start_of_day,
                Task.due_at <= end_of_day,
            )
            .order_by(Task.due_at.asc())
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
