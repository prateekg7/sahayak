"""Unit tests for HealthSummaryService (T7.2)."""

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
    HealthSummaryAction,
    HealthSummaryRequest,
)
from sahayak.modules.health.service.health_log import HealthLogService
from sahayak.modules.health.service.health_summary import HealthSummaryService
from sahayak.shared.users.models import User


@pytest.mark.asyncio
async def test_health_summary_service_lifecycle() -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    user_id = uuid.uuid4()
    current_time = datetime(2026, 3, 20, 10, 0, 0, tzinfo=UTC)

    def advance_clock() -> datetime:
        nonlocal current_time
        current_time += timedelta(minutes=1)
        return current_time

    log_service = HealthLogService(
        session_factory=session_factory,
        clock=advance_clock,
    )
    summary_service = HealthSummaryService(
        session_factory=session_factory,
        clock=advance_clock,
    )

    try:
        async with UnitOfWork(session_factory) as uow:
            uow.session.add(User(id=user_id))
            await uow.session.flush()

        # 1. Initially empty summary
        res_empty, spoken_empty = await summary_service.execute(
            user_id,
            HealthSummaryRequest(action=HealthSummaryAction.TODAY),
        )
        assert res_empty.summary.get("water_ml") == 0
        assert "No health activities logged today" in spoken_empty

        # 2. Add medicine schedule
        res_add_med, spoken_add = await summary_service.execute(
            user_id,
            HealthSummaryRequest(
                action=HealthSummaryAction.ADD_MEDICINE,
                medicine_name="Vitamin C",
                dosage_text="1 chewable tablet",
                times=["09:00", "21:00"],
            ),
        )
        assert res_add_med.action == "add_medicine"
        assert len(res_add_med.medicines) == 1
        assert res_add_med.medicines[0].name == "Vitamin C"
        assert "Added Vitamin C to your schedule" in spoken_add

        # 3. List medicines
        res_list_meds, spoken_list_meds = await summary_service.execute(
            user_id,
            HealthSummaryRequest(action=HealthSummaryAction.LIST_MEDICINES),
        )
        assert len(res_list_meds.medicines) == 1
        assert "Vitamin C" in spoken_list_meds

        # 4. Check medicines due
        res_due, spoken_due = await summary_service.execute(
            user_id,
            HealthSummaryRequest(action=HealthSummaryAction.MEDICINES_DUE),
        )
        assert len(res_due.medicines_due) == 2
        assert "2 medicine doses pending today" in spoken_due

        # 5. Mark 09:00 dose as taken
        res_mark, spoken_mark = await summary_service.execute(
            user_id,
            HealthSummaryRequest(
                action=HealthSummaryAction.MARK_TAKEN,
                medicine_name="Vitamin C",
                scheduled_time="09:00",
            ),
        )
        assert res_mark.action == "mark_taken"
        assert "Marked your Vitamin C for 09:00 as taken" in spoken_mark

        # 6. Check medicines due again (1 pending, 1 taken)
        res_due_after, _ = await summary_service.execute(
            user_id,
            HealthSummaryRequest(action=HealthSummaryAction.MEDICINES_DUE),
        )
        statuses = [d.status for d in res_due_after.medicines_due]
        assert "taken" in statuses
        assert "pending" in statuses

        # 7. Log some health activities today
        await log_service.execute(
            user_id,
            HealthLogRequest(
                action=HealthLogAction.LOG,
                kind="water",
                value=750,
                unit="ml",
            ),
        )
        await log_service.execute(
            user_id,
            HealthLogRequest(
                action=HealthLogAction.LOG,
                kind="workout",
                activity="Yoga",
                duration=30,
                unit="minutes",
            ),
        )

        # 8. Check today summary with logged items
        res_today, spoken_today = await summary_service.execute(
            user_id,
            HealthSummaryRequest(action=HealthSummaryAction.TODAY),
        )
        assert res_today.summary.get("water_ml") == 750
        assert res_today.summary.get("workout_minutes") == 30
        assert res_today.summary.get("medicines_due_count") == 2
        assert res_today.summary.get("medicines_taken_count") == 1
        assert "750 ml water" in spoken_today
        assert "30 minutes of exercise" in spoken_today

        # 9. Check weekly summary
        res_week, spoken_week = await summary_service.execute(
            user_id,
            HealthSummaryRequest(action=HealthSummaryAction.WEEK),
        )
        assert "Past 7 days" in spoken_week
        assert res_week.summary.get("total_workout_minutes") == 30

        # 10. Mark non-existent medicine raises NotFoundError
        with pytest.raises(NotFoundError):
            await summary_service.execute(
                user_id,
                HealthSummaryRequest(
                    action=HealthSummaryAction.MARK_TAKEN,
                    medicine_name="NonExistentDrug",
                ),
            )

        # 11. Add medicine without name raises InvalidInputError
        with pytest.raises(InvalidInputError):
            await summary_service.execute(
                user_id,
                HealthSummaryRequest(
                    action=HealthSummaryAction.ADD_MEDICINE,
                    medicine_name=None,
                ),
            )

    finally:
        await engine.dispose()
