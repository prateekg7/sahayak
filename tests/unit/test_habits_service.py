"""Unit tests for HabitService orchestration, streak computation, and event dispatch (T5.2)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.config import get_settings
from sahayak.core.db.session import UnitOfWork
from sahayak.core.events import DomainEvent, OutboxEventRecord
from sahayak.modules.academics.service.progress import ProgressService
from sahayak.modules.productivity.service.habits import HabitService
from sahayak.shared.users.models import User


@pytest.fixture
def fake_clock() -> datetime:
    return datetime(2026, 10, 23, 10, 0, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_habit_lifecycle_create_log_status_list(fake_clock: datetime) -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    user_id = uuid.uuid4()
    service = HabitService(session_factory=session_factory, clock=lambda: fake_clock)

    try:
        # Seed user
        async with UnitOfWork(session_factory) as uow:
            uow.session.add(User(id=user_id))
            await uow.session.flush()

        # 1. Create habit
        spoken, data, next_actions = await service.create_habit(
            user_id=user_id,
            name="Daily Study",
            frequency="daily",
        )
        assert "Started tracking Daily Study" in spoken
        assert data.habit is not None
        assert data.habit.name == "Daily Study"
        assert data.habit.streak_current == 0
        habit_id = data.habit.id

        # 2. Log habit for today
        spoken_log, data_log, _ = await service.log_habit(
            user_id=user_id,
            name="Daily Study",
        )
        assert "Logged Daily Study for today" in spoken_log
        assert "Streak started" in spoken_log
        assert data_log.habit is not None
        assert data_log.habit.streak_current == 1
        assert data_log.habit.streak_longest == 1

        # Check outbox event was published
        async with UnitOfWork(session_factory) as uow:
            result = await uow.session.execute(
                select(OutboxEventRecord).where(
                    OutboxEventRecord.type == "habit.completed",
                    OutboxEventRecord.payload["user_id"].as_string() == str(user_id),
                )
            )
            outbox_event = result.scalars().first()
            assert outbox_event is not None
            assert outbox_event.payload.get("name") == "Daily Study"
            assert outbox_event.payload.get("streak") == 1

        # 3. Log again today (idempotent; streak stays 1)
        spoken_log2, data_log2, _ = await service.log_habit(
            user_id=user_id,
            habit_id_str=habit_id,
        )
        assert data_log2.habit is not None
        assert data_log2.habit.streak_current == 1

        # 4. Check status
        spoken_stat, data_stat, _ = await service.get_habit_status(
            user_id=user_id,
            name="Daily Study",
        )
        assert "is on a 1 day streak" in spoken_stat
        assert "Completed today" in spoken_stat
        assert data_stat.habit is not None
        assert data_stat.habit.streak_current == 1

        # 5. List habits
        spoken_list, data_list, _ = await service.list_habits(user_id=user_id)
        assert "Daily Study with a 1 day streak" in spoken_list
        assert data_list.count == 1

    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_academics_subscribes_to_study_habit_event(fake_clock: datetime) -> None:
    """Academics ProgressService subscribes to habit.completed and counts study habits."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    user_id = uuid.uuid4()
    habit_service = HabitService(session_factory=session_factory, clock=lambda: fake_clock)
    progress_service = ProgressService(session_factory=session_factory, clock=lambda: fake_clock)

    try:
        # Seed user
        async with UnitOfWork(session_factory) as uow:
            uow.session.add(User(id=user_id))
            await uow.session.flush()

        # Create and log study habit
        await habit_service.create_habit(user_id=user_id, name="Read Biology Textbook")
        await habit_service.log_habit(user_id=user_id, name="Read Biology Textbook")

        # Get the event from outbox
        async with UnitOfWork(session_factory) as uow:
            ev_rec = (
                (
                    await uow.session.execute(
                        select(OutboxEventRecord).where(
                            OutboxEventRecord.type == "habit.completed",
                            OutboxEventRecord.payload["user_id"].as_string() == str(user_id),
                        )
                    )
                )
                .scalars()
                .first()
            )
            assert ev_rec is not None
            event = DomainEvent(
                id=ev_rec.id,
                aggregate=ev_rec.aggregate,
                type=ev_rec.type,
                payload=ev_rec.payload,
                created_at=ev_rec.created_at,
            )

        # Academics processes event
        processed = await progress_service.handle_habit_completed(event)
        assert processed is True

        # Second delivery must be dropped idempotently
        processed_again = await progress_service.handle_habit_completed(event)
        assert processed_again is False

        # Non-study habit is ignored
        non_study_event = DomainEvent(
            id=uuid.uuid4(),
            aggregate="habit",
            type="habit.completed",
            payload={"user_id": str(user_id), "name": "Drink Water"},
            created_at=datetime.now(UTC),
        )
        non_study_res = await progress_service.handle_habit_completed(non_study_event)
        assert non_study_res is True  # Ignored cleanly

    finally:
        await engine.dispose()
