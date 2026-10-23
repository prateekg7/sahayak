"""Integration tests for productivity module GDPR privacy export and deletion (T5.1)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.config import get_settings
from sahayak.core.db.session import UnitOfWork
from sahayak.core.module import Deps
from sahayak.modules.productivity.module import ProductivityModule
from sahayak.modules.productivity.service.tasks import TaskService
from sahayak.shared.users.models import User


@pytest.mark.asyncio
async def test_productivity_privacy_export_and_delete() -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    user_id = uuid.uuid4()
    prod_module = ProductivityModule()
    deps = Deps(session_factory=session_factory)
    prod_module._deps = deps

    service = TaskService(session_factory=session_factory)

    try:
        # Seed user
        async with UnitOfWork(session_factory) as uow:
            uow.session.add(User(id=user_id))
            await uow.session.flush()

        # Seed tasks
        await service.create_task(
            user_id=user_id,
            title="Privacy test task 1",
            list_name="inbox",
            priority="medium",
        )
        await service.create_task(
            user_id=user_id,
            title="Privacy test task 2",
            list_name="work",
            priority="high",
        )

        from sahayak.modules.productivity.service.habits import HabitService
        from sahayak.modules.productivity.service.notes import NoteService

        habit_service = HabitService(session_factory=session_factory)
        await habit_service.create_habit(user_id=user_id, name="Daily Meditation")
        await habit_service.log_habit(user_id=user_id, name="Daily Meditation")

        note_service = NoteService(session_factory=session_factory)
        await note_service.add_note(user_id=user_id, content="Secret privacy note")

        # 1. Export user data
        exported = await prod_module.export_user_data(str(user_id))
        assert "tasks" in exported
        assert "habits" in exported
        assert "habit_logs" in exported
        assert "notes" in exported

        assert len(exported["tasks"]) == 2
        assert len(exported["habits"]) == 1
        assert len(exported["habit_logs"]) == 1
        assert len(exported["notes"]) == 1
        assert exported["habits"][0]["name"] == "Daily Meditation"
        assert exported["notes"][0]["content"] == "Secret privacy note"

        # 2. Delete user data (GDPR erasure)
        await prod_module.delete_user_data(str(user_id))

        # 3. Verify deletion
        exported_after = await prod_module.export_user_data(str(user_id))
        assert exported_after["tasks"] == []
        assert exported_after["habits"] == []
        assert exported_after["habit_logs"] == []
        assert exported_after["notes"] == []

        _, list_after, _ = await service.list_tasks(user_id=user_id, status=None)
        assert list_after.count == 0

    finally:
        await engine.dispose()
