"""Integration tests for health module GDPR privacy export and deletion (T7.1, T7.2)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.config import get_settings
from sahayak.core.db.session import UnitOfWork
from sahayak.core.module import Deps
from sahayak.modules.health.module import HealthModule
from sahayak.modules.health.schemas import (
    HealthLogAction,
    HealthLogRequest,
    HealthSummaryAction,
    HealthSummaryRequest,
)
from sahayak.modules.health.service.health_log import HealthLogService
from sahayak.modules.health.service.health_summary import HealthSummaryService
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

    log_service = HealthLogService(session_factory=session_factory)
    summary_service = HealthSummaryService(session_factory=session_factory)

    try:
        # Seed user
        async with UnitOfWork(session_factory) as uow:
            uow.session.add(User(id=user_id))
            await uow.session.flush()

        # Seed health entries
        await log_service.execute(
            user_id,
            HealthLogRequest(
                action=HealthLogAction.LOG,
                kind="water",
                value=500,
                unit="ml",
            ),
        )
        await log_service.execute(
            user_id,
            HealthLogRequest(
                action=HealthLogAction.LOG,
                kind="meal",
                meal_name="Oatmeal with berries",
                meal_type="breakfast",
                calories=300,
            ),
        )
        await log_service.execute(
            user_id,
            HealthLogRequest(
                action=HealthLogAction.LOG,
                kind="sleep",
                value=7.5,
                unit="hours",
            ),
        )

        # Seed medicine and dose
        await summary_service.execute(
            user_id,
            HealthSummaryRequest(
                action=HealthSummaryAction.ADD_MEDICINE,
                medicine_name="Daily Multi",
                times=["09:00"],
            ),
        )
        await summary_service.execute(
            user_id,
            HealthSummaryRequest(
                action=HealthSummaryAction.MARK_TAKEN,
                medicine_name="Daily Multi",
                scheduled_time="09:00",
            ),
        )

        # 1. Export user data
        exported = await health_module.export_user_data(str(user_id))
        assert "health_entries" in exported
        assert "health_medicines" in exported
        assert "health_medicine_doses" in exported

        entries = exported["health_entries"]
        assert len(entries) == 3
        kinds = {e["kind"] for e in entries}
        assert kinds == {"water", "meal", "sleep"}

        meds = exported["health_medicines"]
        assert len(meds) == 1
        assert meds[0]["name"] == "Daily Multi"

        doses = exported["health_medicine_doses"]
        assert len(doses) == 1
        assert doses[0]["status"] == "taken"

        # 2. Delete user data (GDPR purge)
        await health_module.delete_user_data(str(user_id))

        # 3. Export after delete must be empty across all tables
        exported_after = await health_module.export_user_data(str(user_id))
        assert len(exported_after["health_entries"]) == 0
        assert len(exported_after["health_medicines"]) == 0
        assert len(exported_after["health_medicine_doses"]) == 0

    finally:
        await engine.dispose()
