"""Unit tests for TaskService orchestration and persistence (T5.1)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.config import get_settings
from sahayak.core.db.session import UnitOfWork
from sahayak.core.errors import InvalidInputError, NotFoundError
from sahayak.modules.productivity.service.tasks import TaskService
from sahayak.shared.users.models import User


@pytest.fixture
def fake_clock() -> datetime:
    return datetime(2026, 10, 23, 10, 0, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_task_lifecycle_create_list_complete_reschedule_delete(
    fake_clock: datetime,
) -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    user_id = uuid.uuid4()
    service = TaskService(session_factory=session_factory, clock=lambda: fake_clock)

    try:
        # Seed user
        async with UnitOfWork(session_factory) as uow:
            uow.session.add(User(id=user_id))
            await uow.session.flush()

        # 1. Create task with natural due date
        spoken, data, next_actions = await service.create_task(
            user_id=user_id,
            title="Submit project report",
            due_date_str="tomorrow",
            priority="high",
            list_name="work",
            tags=["urgent"],
        )
        assert "Added task Submit project report" in spoken
        assert "work" in spoken
        assert data.task is not None
        assert data.task.title == "Submit project report"
        assert data.task.priority == "high"
        assert data.task.list_name == "work"
        assert data.task.status == "pending"
        task_id = data.task.id

        # 2. List tasks
        spoken_list, data_list, _ = await service.list_tasks(
            user_id=user_id,
            list_name="work",
            status="pending",
        )
        assert "Submit project report" in spoken_list
        assert data_list.count == 1
        assert data_list.tasks[0].id == task_id

        # 3. Reschedule task
        spoken_resched, data_resched, _ = await service.reschedule_task(
            user_id=user_id,
            task_id_str=task_id,
            due_date_str="in 3 days",
        )
        assert "Rescheduled Submit project report" in spoken_resched
        assert data_resched.task is not None
        assert data_resched.task.due_at is not None

        # 4. Complete task
        spoken_comp, data_comp, _ = await service.complete_task(
            user_id=user_id,
            task_id_str=task_id,
        )
        assert "Marked Submit project report as completed." in spoken_comp
        assert data_comp.task is not None
        assert data_comp.task.status == "completed"
        assert data_comp.task.completed_at is not None

        # Confirm pending list is now empty
        _, data_empty, _ = await service.list_tasks(
            user_id=user_id,
            list_name="work",
            status="pending",
        )
        assert data_empty.count == 0

        # 5. Delete task
        spoken_del, data_del, _ = await service.delete_task(
            user_id=user_id,
            task_id_str=task_id,
        )
        assert "Deleted task Submit project report." in spoken_del
        assert data_del.task is not None

        # Deleting again raises NotFoundError
        with pytest.raises(NotFoundError):
            await service.delete_task(user_id=user_id, task_id_str=task_id)

    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_task_service_validation(fake_clock: datetime) -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    user_id = uuid.uuid4()
    service = TaskService(session_factory=session_factory, clock=lambda: fake_clock)

    try:
        # Empty title
        with pytest.raises(InvalidInputError) as exc_title:
            await service.create_task(user_id=user_id, title="")
        assert "title cannot be empty" in str(exc_title.value)

        # Invalid task id
        with pytest.raises(InvalidInputError):
            await service.complete_task(user_id=user_id, task_id_str="not-a-uuid")

        # Non-existent task id
        random_id = str(uuid.uuid4())
        with pytest.raises(NotFoundError):
            await service.complete_task(user_id=user_id, task_id_str=random_id)

    finally:
        await engine.dispose()
