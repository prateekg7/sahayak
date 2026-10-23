"""Unit tests for BriefingService orchestration and cross-module adaptation (T5.5)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.config import get_settings
from sahayak.core.db.session import UnitOfWork
from sahayak.modules.productivity.service.briefing import BriefingService
from sahayak.modules.productivity.service.habits import HabitService
from sahayak.modules.productivity.service.tasks import TaskService
from sahayak.shared.users.models import User


class FakeAcademicsAPI:
    """Mock implementation of AcademicsAPIPort for testing cross-module briefing."""

    def __init__(
        self,
        streak: int = 5,
        due_cards: int = 7,
        study_tasks: list[str] | None = None,
    ) -> None:
        self.streak = streak
        self.due_cards = due_cards
        self.study_tasks = study_tasks or ["Cell Biology", "Organic Reactions"]

    async def get_streak(self, user_id: str | uuid.UUID, timezone_str: str = "UTC") -> int:
        return self.streak

    async def get_due_flashcard_count(
        self, user_id: str | uuid.UUID, before: datetime | None = None
    ) -> int:
        return self.due_cards

    async def get_today_study_tasks(
        self, user_id: str | uuid.UUID, timezone_str: str = "UTC"
    ) -> list[str]:
        return list(self.study_tasks)


@pytest.mark.asyncio
async def test_briefing_with_academics_enabled() -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    user_id = uuid.uuid4()
    fixed_now = datetime(2026, 10, 23, 10, 0, 0, tzinfo=UTC)

    fake_acad = FakeAcademicsAPI(streak=3, due_cards=4, study_tasks=["Organic Chemistry"])
    service = BriefingService(
        session_factory=session_factory,
        academics_api_getter=lambda: fake_acad,
        clock=lambda: fixed_now,
    )

    task_service = TaskService(session_factory=session_factory, clock=lambda: fixed_now)
    habit_service = HabitService(session_factory=session_factory, clock=lambda: fixed_now)

    try:
        # Seed user
        async with UnitOfWork(session_factory) as uow:
            uow.session.add(User(id=user_id))
            await uow.session.flush()

        # Seed task due today
        await task_service.create_task(
            user_id=user_id,
            title="Submit project report",
            due_date_str="today",
        )

        # Seed habit
        await habit_service.create_habit(user_id=user_id, name="Daily Stretching")

        spoken, data, next_actions = await service.get_daily_briefing(user_id=user_id)

        assert data.academics_enabled is True
        assert data.tasks_due_count == 1
        assert "Submit project report" in data.tasks_due
        assert data.habits_pending_count == 1
        assert "Daily Stretching" in data.habits_pending
        assert data.flashcards_due_count == 4
        assert data.study_tasks == ["Organic Chemistry"]
        assert data.study_streak == 3

        assert "1 task due today: Submit project report" in spoken
        assert "Daily Stretching" in spoken
        assert "4 cards due" in spoken
        assert "1 study tasks" in spoken
        assert "review flashcards" in next_actions

    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_briefing_adapts_when_academics_disabled() -> None:
    """When academics module is not loaded / disabled, briefing omits academics gracefully."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    user_id = uuid.uuid4()
    fixed_now = datetime(2026, 10, 23, 10, 0, 0, tzinfo=UTC)

    # academics_api_getter returns None (simulating module disabled in registry)
    service = BriefingService(
        session_factory=session_factory,
        academics_api_getter=lambda: None,
        clock=lambda: fixed_now,
    )

    task_service = TaskService(session_factory=session_factory, clock=lambda: fixed_now)

    try:
        # Seed user
        async with UnitOfWork(session_factory) as uow:
            uow.session.add(User(id=user_id))
            await uow.session.flush()

        await task_service.create_task(
            user_id=user_id,
            title="Renew passport",
            due_date_str="today",
        )

        spoken, data, next_actions = await service.get_daily_briefing(user_id=user_id)

        assert data.academics_enabled is False
        assert data.flashcards_due_count is None
        assert data.study_tasks == []
        assert data.study_streak is None
        assert data.tasks_due_count == 1
        assert "Renew passport" in data.tasks_due

        assert "Renew passport" in spoken
        assert "academics" not in spoken
        assert "flashcards" not in spoken
        assert "review flashcards" not in next_actions

    finally:
        await engine.dispose()
