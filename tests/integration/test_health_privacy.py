"""Integration tests for health module GDPR privacy export and deletion (T7.1)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.config import get_settings
from sahayak.core.db.session import UnitOfWork
from sahayak.core.module import Deps
from sahayak.modules.health.module import HealthModule
from sahayak.modules.health.schemas import HealthLogAction, HealthLogRequest
from sahayak.modules.health.service.health_log import HealthLogService
from sahayak.shared.users.models import User


@pytest.mark.asyncio
async def test_health_privacy_export_and_delete() -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    user_id = uuid.uuid4()
    health_module = HealthModule()
    deps = Deps(session_factory=session_factory)
    health_module._deps = deps

    service = HealthLogService(session_factory=session_factory)

    try:
        # Seed user
        async with UnitOfWork(session_factory) as uow:
            uow.session.add(User(id=user_id))
            await uow.session.flush()

        # Seed health entries
        await service.execute(
            user_id,
            HealthLogRequest(
                action=HealthLogAction.LOG,
                kind="water",
                value=500,
                unit="ml",
            ),
        )
        await service.execute(
            user_id,
            HealthLogRequest(
                action=HealthLogAction.LOG,
                kind="meal",
                meal_name="Oatmeal with berries",
                meal_type="breakfast",
                calories=300,
            ),
        )
        await service.execute(
            user_id,
            HealthLogRequest(
                action=HealthLogAction.LOG,
                kind="sleep",
                value=7.5,
                unit="hours",
            ),
        )

        # 1. Export user data
        exported = await health_module.export_user_data(str(user_id))
        assert "health_entries" in exported
        entries = exported["health_entries"]
        assert len(entries) == 3
        kinds = {e["kind"] for e in entries}
        assert kinds == {"water", "meal", "sleep"}

        # 2. Delete user data (GDPR purge)
        await health_module.delete_user_data(str(user_id))

        # 3. Export after delete must be empty
        exported_after = await health_module.export_user_data(str(user_id))
        assert len(exported_after["health_entries"]) == 0

    finally:
        await engine.dispose()
