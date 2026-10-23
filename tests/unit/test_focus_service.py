"""Unit tests for FocusService orchestration, fake clock, and history (T5.4)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.config import get_settings
from sahayak.core.db.session import UnitOfWork
from sahayak.core.errors import InvalidInputError, NotFoundError
from sahayak.modules.productivity.service.focus import FocusService
from sahayak.shared.users.models import User


@pytest.mark.asyncio
async def test_focus_timer_lifecycle_under_fake_clock() -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    user_id = uuid.uuid4()
    current_time = datetime(2026, 10, 23, 10, 0, 0, tzinfo=UTC)

    service = FocusService(
        session_factory=session_factory,
        clock=lambda: current_time,
    )

    try:
        # Seed user
        async with UnitOfWork(session_factory) as uow:
            uow.session.add(User(id=user_id))
            await uow.session.flush()

        # 1. No active session initially
        spoken_init, data_init, _ = await service.get_session_status(user_id=user_id)
        assert "not have an active focus session" in spoken_init
        assert data_init.session is None

        # 2. Start a 25-minute session
        spoken_start, data_start, _ = await service.start_session(
            user_id=user_id,
            duration_minutes=25,
            task_label="Quantum Physics",
        )
        assert "Started a 25 minute focus session for Quantum Physics" in spoken_start
        assert data_start.session is not None
        assert data_start.session.status == "active"
        assert data_start.session.remaining_seconds == 25 * 60

        # 3. Try to start another session while active -> informs of active session
        current_time += timedelta(minutes=5)
        spoken_dup, data_dup, _ = await service.start_session(
            user_id=user_id,
            duration_minutes=30,
        )
        assert "already have an active focus session with 20 minutes remaining" in spoken_dup
        assert data_dup.session is not None
        assert data_dup.session.remaining_seconds == 20 * 60

        # 4. Check status mid-session
        current_time += timedelta(minutes=10)  # now 15 minutes elapsed, 10 left
        spoken_stat, data_stat, _ = await service.get_session_status(user_id=user_id)
        assert "10 minutes remaining" in spoken_stat
        assert data_stat.session is not None
        assert data_stat.session.remaining_seconds == 10 * 60

        # 5. Advance time past planned end (now 26 minutes elapsed)
        current_time += timedelta(minutes=11)
        spoken_done, data_done, _ = await service.get_session_status(user_id=user_id)
        assert "is finished. Great job staying focused." in spoken_done
        assert data_done.session is not None
        assert data_done.session.status == "completed"
        assert data_done.session.remaining_seconds == 0

        # 6. Start another session and stop it early
        current_time += timedelta(minutes=5)
        await service.start_session(
            user_id=user_id, duration_minutes=30, task_label="Chemistry lab"
        )
        current_time += timedelta(minutes=12)
        spoken_stop, data_stop, _ = await service.stop_session(user_id=user_id)
        assert "stopped after 12 minutes." in spoken_stop
        assert data_stop.session is not None
        assert data_stop.session.status == "cancelled"

        # 7. Check history
        spoken_hist, data_hist, _ = await service.get_history(user_id=user_id)
        assert "completed 1 focus session totaling 25 minutes" in spoken_hist
        assert data_hist.stats is not None
        assert data_hist.stats.total_completed == 1
        assert data_hist.stats.total_minutes_focused == 25
        assert data_hist.stats.today_completed == 1
        assert len(data_hist.sessions) == 2

    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_focus_service_errors() -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    user_id = uuid.uuid4()
    service = FocusService(session_factory=session_factory)

    try:
        # Invalid duration
        with pytest.raises(InvalidInputError):
            await service.start_session(user_id=user_id, duration_minutes=0)

        with pytest.raises(InvalidInputError):
            await service.start_session(user_id=user_id, duration_minutes=200)

        # Stop when no active session
        with pytest.raises(NotFoundError):
            await service.stop_session(user_id=user_id)

    finally:
        await engine.dispose()
