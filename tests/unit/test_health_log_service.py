"""Unit tests for HealthLogService (T7.1)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.config import get_settings
from sahayak.core.db.session import UnitOfWork
from sahayak.core.errors import InvalidInputError, NotFoundError
from sahayak.modules.health.schemas import (
    HealthLogAction,
    HealthLogRequest,
)
from sahayak.modules.health.service.health_log import HealthLogService
from sahayak.shared.users.models import User


@pytest.mark.asyncio
async def test_health_log_service_lifecycle() -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    user_id = uuid.uuid4()
    current_time = datetime(2026, 3, 20, 10, 0, 0, tzinfo=UTC)

    def advance_clock() -> datetime:
        nonlocal current_time
        current_time += timedelta(minutes=1)
        return current_time

    service = HealthLogService(
        session_factory=session_factory,
        clock=advance_clock,
    )

    try:
        async with UnitOfWork(session_factory) as uow:
            uow.session.add(User(id=user_id))
            await uow.session.flush()

        # 1. Log water entry
        res_water, spoken_water = await service.execute(
            user_id,
            HealthLogRequest(
                action=HealthLogAction.LOG,
                kind="water",
                value=500,
                unit="ml",
            ),
        )
        assert res_water.action == "log"
        assert res_water.entry is not None
        assert res_water.entry.data.get("amount_ml") == 500
        assert "Logged 500 ml of water" in spoken_water
        water_id = res_water.entry.id

        # 2. Log second water entry (glasses)
        res_water2, spoken_water2 = await service.execute(
            user_id,
            HealthLogRequest(
                action=HealthLogAction.LOG,
                kind="water",
                value=2,
                unit="glasses",
            ),
        )
        assert res_water2.entry is not None
        assert res_water2.entry.data.get("amount_ml") == 500

        # 3. List water entries
        res_list, spoken_list = await service.execute(
            user_id,
            HealthLogRequest(
                action=HealthLogAction.LIST,
                kind="water",
                limit=10,
            ),
        )
        assert res_list.count == 2
        assert "Your recent logs" in spoken_list
        assert "500 ml water" in spoken_list

        # 4. Undo last water entry
        res_undo, spoken_undo = await service.execute(
            user_id,
            HealthLogRequest(
                action=HealthLogAction.UNDO_LAST,
                kind="water",
            ),
        )
        assert res_undo.action == "undo_last"
        assert "Undid your last water log" in spoken_undo

        # 5. List again, should have 1 entry left
        res_list_after, _ = await service.execute(
            user_id,
            HealthLogRequest(
                action=HealthLogAction.LIST,
                kind="water",
            ),
        )
        assert res_list_after.count == 1
        assert res_list_after.entries[0].id == water_id

        # 6. Log meal
        res_meal, spoken_meal = await service.execute(
            user_id,
            HealthLogRequest(
                action=HealthLogAction.LOG,
                kind="meal",
                meal_name="Avocado toast",
                meal_type="breakfast",
                calories=350,
            ),
        )
        assert res_meal.entry is not None
        assert "Logged breakfast: Avocado toast" in spoken_meal
        meal_id = res_meal.entry.id

        # 7. Log workout
        res_workout, spoken_workout = await service.execute(
            user_id,
            HealthLogRequest(
                action=HealthLogAction.LOG,
                kind="workout",
                activity="Swimming",
                duration=40,
                unit="minutes",
            ),
        )
        assert res_workout.entry is not None
        assert "Logged 40 minutes of Swimming" in spoken_workout

        # 8. Log sleep
        res_sleep, spoken_sleep = await service.execute(
            user_id,
            HealthLogRequest(
                action=HealthLogAction.LOG,
                kind="sleep",
                value=8,
                unit="hours",
            ),
        )
        assert res_sleep.entry is not None
        assert "Logged 8.0 hours of sleep" in spoken_sleep

        # 9. Delete meal by ID
        res_del, spoken_del = await service.execute(
            user_id,
            HealthLogRequest(
                action=HealthLogAction.DELETE,
                entry_id=meal_id,
            ),
        )
        assert res_del.action == "delete"
        assert "Deleted" in spoken_del

        # 10. Deleting already deleted or non-existent entry raises NotFoundError
        with pytest.raises(NotFoundError):
            await service.execute(
                user_id,
                HealthLogRequest(
                    action=HealthLogAction.DELETE,
                    entry_id=meal_id,
                ),
            )

        # 11. Delete without entry_id raises InvalidInputError
        with pytest.raises(InvalidInputError, match="Entry ID is required"):
            await service.execute(
                user_id,
                HealthLogRequest(
                    action=HealthLogAction.DELETE,
                    entry_id=None,
                ),
            )

    finally:
        await engine.dispose()
