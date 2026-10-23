"""Unit tests for ProgressService, event handlers, and progress_report tool (T3.13)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.auth.principal import Principal, set_current_principal
from sahayak.core.config import get_settings
from sahayak.core.db.session import UnitOfWork
from sahayak.core.events import DomainEvent
from sahayak.modules.academics.domain.topics import normalize_topic
from sahayak.modules.academics.models import ActivityLog, Deck, Topic, TopicStats
from sahayak.modules.academics.schemas import ProgressReportRequest
from sahayak.modules.academics.service.progress import ProgressService
from sahayak.modules.academics.tools.progress import (
    progress_report,
    set_progress_service,
)
from sahayak.shared.users.models import User


@pytest.fixture
def progress_env() -> tuple[ProgressService, async_sessionmaker[Any]]:
    """Provision a ProgressService backed by real PostgreSQL session factory."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    fixed_now = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)
    service = ProgressService(
        session_factory=session_factory,
        clock=lambda: fixed_now,
    )
    set_progress_service(service)
    return service, session_factory


@pytest.mark.asyncio
async def test_quiz_finished_event_updates_topic_stats_and_is_idempotent(
    progress_env: tuple[ProgressService, async_sessionmaker[Any]],
) -> None:
    """Quiz finished event updates topic stats and deduplicates subsequent deliveries."""
    service, session_factory = progress_env
    user_id = uuid.uuid4()
    async with UnitOfWork(session_factory) as uow:
        uow.session.add(User(id=user_id))
        await uow.session.flush()

    event_id = uuid.uuid4()
    created_at = datetime(2026, 10, 23, 10, 30, tzinfo=UTC)
    event = DomainEvent(
        id=event_id,
        aggregate="quiz",
        type="academics.quiz.finished",
        payload={
            "quiz_id": str(uuid.uuid4()),
            "user_id": str(user_id),
            "topic_key": "photosynthesis",
            "topic_name": "Photosynthesis",
            "score": 4,
            "total_questions": 5,
            "percentage": 80.0,
        },
        created_at=created_at,
    )

    # 1. First event processing
    processed = await service.handle_quiz_finished(event)
    assert processed is True

    async with UnitOfWork(session_factory) as uow:
        topic_res = await uow.session.execute(
            select(Topic).where(Topic.topic_key == "photosynthesis")
        )
        topic = topic_res.scalar_one()

        stats_res = await uow.session.execute(
            select(TopicStats).where(TopicStats.user_id == user_id, TopicStats.topic_id == topic.id)
        )
        stats = stats_res.scalar_one()
        assert stats.attempts == 5
        assert stats.correct == 4

        # Verify activity_log
        log_res = await uow.session.execute(
            select(ActivityLog).where(ActivityLog.event_id == event_id)
        )
        log = log_res.scalar_one()
        assert log.activity_type == "quiz"
        assert log.user_id == user_id

    # 2. Duplicate delivery must be ignored (idempotent)
    second_processed = await service.handle_quiz_finished(event)
    assert second_processed is False

    # Stats must remain unchanged (not double-counted)
    async with UnitOfWork(session_factory) as uow:
        stats_res2 = await uow.session.execute(
            select(TopicStats).where(TopicStats.user_id == user_id, TopicStats.topic_id == topic.id)
        )
        stats2 = stats_res2.scalar_one()
        assert stats2.attempts == 5
        assert stats2.correct == 4


@pytest.mark.asyncio
async def test_flashcard_graded_event_updates_deck_topic_stats(
    progress_env: tuple[ProgressService, async_sessionmaker[Any]],
) -> None:
    """Flashcard graded event maps deck name to topic and updates accuracy."""
    service, session_factory = progress_env
    user_id = uuid.uuid4()
    deck_id = uuid.uuid4()

    async with UnitOfWork(session_factory) as uow:
        uow.session.add(User(id=user_id))
        await uow.session.flush()

    async with UnitOfWork(session_factory) as uow:
        deck = Deck(id=deck_id, user_id=user_id, name="Organic Chemistry")
        uow.session.add(deck)
        await uow.session.flush()

    # Event with "good" rating (correct recall)
    event1 = DomainEvent(
        id=uuid.uuid4(),
        aggregate="flashcard",
        type="academics.flashcard.graded",
        payload={
            "user_id": str(user_id),
            "card_id": str(uuid.uuid4()),
            "deck_id": str(deck_id),
            "rating": "good",
        },
        created_at=datetime(2026, 10, 23, 11, 0, tzinfo=UTC),
    )
    assert await service.handle_flashcard_graded(event1) is True

    # Event with "hard" rating (incorrect/difficult recall)
    event2 = DomainEvent(
        id=uuid.uuid4(),
        aggregate="flashcard",
        type="academics.flashcard.graded",
        payload={
            "user_id": str(user_id),
            "card_id": str(uuid.uuid4()),
            "deck_id": str(deck_id),
            "rating": "hard",
        },
        created_at=datetime(2026, 10, 23, 11, 5, tzinfo=UTC),
    )
    assert await service.handle_flashcard_graded(event2) is True

    # Verify topic stats: 2 attempts, 1 correct
    async with UnitOfWork(session_factory) as uow:
        topic_key, _ = normalize_topic("Organic Chemistry")
        topic_res = await uow.session.execute(select(Topic).where(Topic.topic_key == topic_key))
        topic = topic_res.scalar_one()

        stats_res = await uow.session.execute(
            select(TopicStats).where(TopicStats.user_id == user_id, TopicStats.topic_id == topic.id)
        )
        stats = stats_res.scalar_one()
        assert stats.attempts == 2
        assert stats.correct == 1


@pytest.mark.asyncio
async def test_anonymous_events_are_skipped_without_error(
    progress_env: tuple[ProgressService, async_sessionmaker[Any]],
) -> None:
    """Events without a user_id do not create persistent stats."""
    service, _ = progress_env
    anon_event = DomainEvent(
        id=uuid.uuid4(),
        aggregate="quiz",
        type="academics.quiz.finished",
        payload={
            "quiz_id": str(uuid.uuid4()),
            "user_id": None,
            "topic_key": "astronomy",
            "score": 3,
            "total_questions": 3,
        },
        created_at=datetime.now(UTC),
    )
    assert await service.handle_quiz_finished(anon_event) is True


@pytest.mark.asyncio
async def test_progress_report_scopes(
    progress_env: tuple[ProgressService, async_sessionmaker[Any]],
) -> None:
    """Test get_progress_report with all scopes: summary, weak_topics, streak, weekly."""
    service, session_factory = progress_env
    user_id = uuid.uuid4()

    async with UnitOfWork(session_factory) as uow:
        uow.session.add(User(id=user_id))
        await uow.session.flush()

    # Simulate activity across 3 consecutive days:
    # today (Oct 23), yesterday (Oct 22), 2 days ago (Oct 21)
    for day_offset in range(3):
        ts = datetime(2026, 10, 23 - day_offset, 10, 0, tzinfo=UTC)
        ev = DomainEvent(
            id=uuid.uuid4(),
            aggregate="quiz",
            type="academics.quiz.finished",
            payload={
                "quiz_id": str(uuid.uuid4()),
                "user_id": str(user_id),
                "topic_key": "cell_biology" if day_offset == 0 else "organic_chemistry",
                "topic_name": "Cell Biology" if day_offset == 0 else "Organic Chemistry",
                "score": 2 if day_offset == 0 else 5,
                "total_questions": 5,
                "percentage": 40.0 if day_offset == 0 else 100.0,
            },
            created_at=ts,
        )
        await service.handle_quiz_finished(ev)

    # 1. Scope: summary
    spoken, data, actions = await service.get_progress_report(
        user_id=user_id, scope="summary", user_timezone="UTC"
    )
    assert "study streak is 3 days" in spoken
    assert data.scope == "summary"
    assert data.streak.current_streak == 3
    assert data.streak.longest_streak == 3
    assert data.streak.studied_today is True
    assert len(actions) == 2

    # 2. Scope: weak_topics
    spoken_weak, data_weak, actions_weak = await service.get_progress_report(
        user_id=user_id, scope="weak_topics", user_timezone="UTC"
    )
    assert "weakest topic is Cell Biology" in spoken_weak
    assert data_weak.weak_topics is not None
    assert len(data_weak.weak_topics) >= 1
    assert data_weak.weak_topics[0].topic == "Cell Biology"
    assert data_weak.weak_topics[0].accuracy_pct == 40.0

    # 3. Scope: streak
    spoken_streak, data_streak, _ = await service.get_progress_report(
        user_id=user_id, scope="streak", user_timezone="UTC"
    )
    assert "3 day study streak" in spoken_streak
    assert "already studied today" in spoken_streak

    # 4. Scope: weekly
    spoken_weekly, data_weekly, _ = await service.get_progress_report(
        user_id=user_id, scope="weekly", user_timezone="UTC"
    )
    assert "3 of 7 days" in spoken_weekly
    assert data_weekly.weekly is not None
    assert data_weekly.weekly.active_days == 3


@pytest.mark.asyncio
async def test_progress_report_tool_auth_and_execution(
    progress_env: tuple[ProgressService, async_sessionmaker[Any]],
) -> None:
    """progress_report MCP tool enforces auth and returns valid envelope."""
    service, session_factory = progress_env
    user_id = uuid.uuid4()

    async with UnitOfWork(session_factory) as uow:
        uow.session.add(User(id=user_id))
        await uow.session.flush()

    # 1. Anonymous caller receives auth_required envelope
    set_current_principal(Principal(user_id=None, anonymous=True))
    anon_envelope = await progress_report(ProgressReportRequest(scope="summary"))
    assert anon_envelope.get("ok") is False
    assert anon_envelope.get("error_code") == "auth_required"

    # 2. Authenticated caller succeeds
    set_current_principal(
        Principal(user_id=user_id, scopes=frozenset(["academics:read"]), anonymous=False)
    )
    envelope = await progress_report(ProgressReportRequest(scope="streak"))
    assert envelope.get("ok") is True
    assert envelope.get("spoken_summary") != ""
    assert envelope.get("data") is not None
    assert envelope.get("data", {}).get("streak", {}).get("current_streak") == 0


@pytest.mark.asyncio
async def test_progress_report_cross_day_timezone_streak(
    progress_env: tuple[ProgressService, async_sessionmaker[Any]],
) -> None:
    """Verify streak calculation correctly resolves midnight boundary in user timezone."""
    service, session_factory = progress_env
    user_id = uuid.uuid4()

    async with UnitOfWork(session_factory) as uow:
        uow.session.add(User(id=user_id))
        await uow.session.flush()

    # Activity at 2026-10-22 23:30 UTC.
    # In Asia/Kolkata (+05:30), this timestamp is 2026-10-23 05:00 AM (Today!)
    ts = datetime(2026, 10, 22, 23, 30, tzinfo=UTC)
    ev = DomainEvent(
        id=uuid.uuid4(),
        aggregate="quiz",
        type="academics.quiz.finished",
        payload={
            "quiz_id": str(uuid.uuid4()),
            "user_id": str(user_id),
            "topic_key": "mechanics",
            "topic_name": "Mechanics",
            "score": 3,
            "total_questions": 3,
        },
        created_at=ts,
    )
    await service.handle_quiz_finished(ev)

    # In Asia/Kolkata where today is Oct 23, studied_today is True and current streak is 1
    _, data_kolkata, _ = await service.get_progress_report(
        user_id=user_id, scope="streak", user_timezone="Asia/Kolkata"
    )
    assert data_kolkata.streak.studied_today is True
    assert data_kolkata.streak.current_streak == 1
