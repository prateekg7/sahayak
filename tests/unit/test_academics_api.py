"""Unit tests for Academics cross-module API (T3.15)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.config import get_settings
from sahayak.core.db.session import UnitOfWork
from sahayak.core.module import Deps
from sahayak.modules.academics.adapters.progress import SQLAlchemyProgressRepository
from sahayak.modules.academics.adapters.question_bank import SQLAlchemyQuestionBank
from sahayak.modules.academics.api import AcademicsAPI, AcademicsModuleAPI
from sahayak.modules.academics.module import AcademicsModule
from sahayak.shared.users.models import User


@pytest.mark.asyncio
async def test_academics_api_streak_and_info() -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    user_id = uuid.uuid4()
    fixed_now = datetime(2026, 10, 23, 14, 0, 0, tzinfo=UTC)

    def clock() -> datetime:
        return fixed_now

    async with UnitOfWork(session_factory) as uow:
        uow.session.add(User(id=user_id))
        await uow.session.commit()

    api = AcademicsAPI(session_factory=session_factory, clock=clock)
    assert isinstance(api, AcademicsModuleAPI)

    # 1. Initially no streak
    initial_streak = await api.get_streak(user_id)
    assert initial_streak == 0
    info = await api.get_streak_info(user_id)
    assert info.current_streak == 0
    assert not info.studied_today

    # 2. Add activity today and yesterday
    async with UnitOfWork(session_factory) as uow:
        repo = SQLAlchemyProgressRepository(uow.session)
        await repo.record_activity(
            user_id=user_id,
            activity_type="quiz",
            event_id=uuid.uuid4(),
            created_at=fixed_now - timedelta(days=1),
        )
        await repo.record_activity(
            user_id=user_id,
            activity_type="quiz",
            event_id=uuid.uuid4(),
            created_at=fixed_now,
        )
        await uow.session.commit()

    # 3. Verify streak updated to 2
    streak = await api.get_streak(user_id)
    assert streak == 2
    info = await api.get_streak_info(user_id)
    assert info.current_streak == 2
    assert info.studied_today


@pytest.mark.asyncio
async def test_academics_api_weak_topics() -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    user_id = uuid.uuid4()
    api = AcademicsAPI(session_factory=session_factory)

    async with UnitOfWork(session_factory) as uow:
        uow.session.add(User(id=user_id))
        bank = SQLAlchemyQuestionBank(uow.session)
        progress = SQLAlchemyProgressRepository(uow.session)

        t1 = await bank.get_or_create_topic(f"genetics_{uuid.uuid4().hex[:6]}", "Genetics")
        t2 = await bank.get_or_create_topic(f"ecology_{uuid.uuid4().hex[:6]}", "Ecology")
        t3 = await bank.get_or_create_topic(f"optics_{uuid.uuid4().hex[:6]}", "Optics")

        now = datetime.now(UTC)
        # Genetics: 2/10 = 20%
        await progress.update_topic_stats(
            user_id, t1.id, attempts_delta=10, correct_delta=2, timestamp=now
        )
        # Ecology: 4/10 = 40%
        await progress.update_topic_stats(
            user_id, t2.id, attempts_delta=10, correct_delta=4, timestamp=now
        )
        # Optics: 9/10 = 90%
        await progress.update_topic_stats(
            user_id, t3.id, attempts_delta=10, correct_delta=9, timestamp=now
        )
        await uow.session.commit()

    weak = await api.get_weak_topics(user_id, limit=2)
    assert len(weak) == 2
    assert weak[0] == "Genetics"
    assert weak[1] == "Ecology"


@pytest.mark.asyncio
async def test_academics_api_weekly_summary() -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    user_id = uuid.uuid4()
    fixed_now = datetime(2026, 10, 23, 14, 0, 0, tzinfo=UTC)

    def clock() -> datetime:
        return fixed_now

    async with UnitOfWork(session_factory) as uow:
        uow.session.add(User(id=user_id))
        repo = SQLAlchemyProgressRepository(uow.session)
        # Record 2 activities within the last 7 days
        await repo.record_activity(
            user_id=user_id,
            activity_type="quiz",
            event_id=uuid.uuid4(),
            created_at=fixed_now - timedelta(days=2),
        )
        await repo.record_activity(
            user_id=user_id,
            activity_type="flashcard",
            event_id=uuid.uuid4(),
            created_at=fixed_now,
        )
        await uow.session.commit()

    api = AcademicsAPI(session_factory=session_factory, clock=clock)
    summary = await api.get_weekly_summary(user_id)
    assert summary["active_days"] == 2
    assert "accuracy_pct" in summary


def test_academics_module_api_access() -> None:
    mod = AcademicsModule()
    # Before registration with deps, accessing api raises RuntimeError
    with pytest.raises(RuntimeError, match="not been initialized with dependencies"):
        _ = mod.api

    # With dummy deps and session_factory
    dummy_deps = Deps(session_factory="dummy_session_factory")
    mod.register_tools(mcp=None, deps=dummy_deps)
    api = mod.api
    assert isinstance(api, AcademicsAPI)
