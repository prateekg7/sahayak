"""Unit tests for FlashcardService and SM-2 review orchestration (T3.9)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.config import get_settings
from sahayak.core.db.session import UnitOfWork
from sahayak.core.errors import InvalidInputError, NotFoundError
from sahayak.core.events import OutboxEventRecord
from sahayak.modules.academics.service.flashcards import FlashcardService
from sahayak.shared.users.models import User


@pytest.fixture
def fake_clock() -> datetime:
    return datetime(2026, 10, 23, 15, 0, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_add_card_creates_deck_and_card(fake_clock: datetime) -> None:
    """Adding a flashcard creates default deck if absent and initializes SM-2 parameters."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    user_id = uuid.uuid4()
    service = FlashcardService(session_factory=session_factory, clock=lambda: fake_clock)

    try:
        async with UnitOfWork(session_factory) as uow:
            uow.session.add(User(id=user_id))
            await uow.session.flush()

        card = await service.add_card(
            user_id=user_id,
            front="Mitochondria",
            back="Powerhouse of the cell",
        )

        assert card.id is not None
        assert card.front == "Mitochondria"
        assert card.back == "Powerhouse of the cell"
        assert card.ease == 2.5
        assert card.interval_days == 0
        assert card.repetitions == 0
        assert card.due_at == fake_clock
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_add_card_validation(fake_clock: datetime) -> None:
    """Empty front or back content is rejected with InvalidInputError."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    service = FlashcardService(session_factory=session_factory, clock=lambda: fake_clock)
    user_id = uuid.uuid4()

    try:
        with pytest.raises(InvalidInputError, match="front of the flashcard"):
            await service.add_card(user_id=user_id, front="   ", back="Valid back")

        with pytest.raises(InvalidInputError, match="back of the flashcard"):
            await service.add_card(user_id=user_id, front="Valid front", back="")

        with pytest.raises(InvalidInputError, match="too long"):
            await service.add_card(user_id=user_id, front="A" * 2001, back="Back")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_grade_card_advances_sm2_and_emits_event(fake_clock: datetime) -> None:
    """Grading card updates ease and interval, reschedules due_at,
    and writes to transactional outbox.
    """
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    user_id = uuid.uuid4()
    service = FlashcardService(session_factory=session_factory, clock=lambda: fake_clock)

    try:
        async with UnitOfWork(session_factory) as uow:
            uow.session.add(User(id=user_id))
            await uow.session.flush()

        card = await service.add_card(
            user_id=user_id,
            front="Newton's First Law",
            back="An object at rest stays at rest",
            deck_name="Physics",
        )

        # Grade 1: 'good' -> interval 1 day
        graded_1 = await service.grade_card(user_id=user_id, card_id=card.id, rating="good")
        assert graded_1.repetitions == 1
        assert graded_1.interval_days == 1
        assert graded_1.ease == 2.5
        assert graded_1.due_at == fake_clock + timedelta(days=1)

        # Grade 2: simulate review next day
        day_2_clock = fake_clock + timedelta(days=1)
        service_day_2 = FlashcardService(session_factory=session_factory, clock=lambda: day_2_clock)

        graded_2 = await service_day_2.grade_card(user_id=user_id, card_id=card.id, rating="good")
        assert graded_2.repetitions == 2
        assert graded_2.interval_days == 6
        assert graded_2.due_at == day_2_clock + timedelta(days=6)

        # Verify domain event in transactional outbox
        async with UnitOfWork(session_factory) as uow:
            stmt = (
                select(OutboxEventRecord)
                .where(OutboxEventRecord.type == "academics.flashcard.graded")
                .order_by(OutboxEventRecord.created_at.desc())
            )
            res = await uow.session.execute(stmt)
            event = res.scalars().first()
            assert event is not None
            assert event.payload["card_id"] == str(card.id)
            assert event.payload["rating"] == "good"
            assert event.payload["interval_days"] == 6
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_grade_card_errors(fake_clock: datetime) -> None:
    """Grading non-existent card or passing invalid rating raises expected domain errors."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    user_id = uuid.uuid4()
    service = FlashcardService(session_factory=session_factory, clock=lambda: fake_clock)

    try:
        # Invalid rating
        with pytest.raises(InvalidInputError, match="again, hard, good, or easy"):
            await service.grade_card(user_id=user_id, card_id=uuid.uuid4(), rating="awesome")

        # Non-existent card
        with pytest.raises(NotFoundError, match="couldn't find that flashcard"):
            await service.grade_card(user_id=user_id, card_id=uuid.uuid4(), rating="good")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_get_next_due_and_list_due(fake_clock: datetime) -> None:
    """Querying due cards returns cards with due_at <= now in ascending order."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    user_id = uuid.uuid4()
    service = FlashcardService(session_factory=session_factory, clock=lambda: fake_clock)

    try:
        async with UnitOfWork(session_factory) as uow:
            uow.session.add(User(id=user_id))
            await uow.session.flush()

        # Add 3 cards in Biology
        c1 = await service.add_card(user_id=user_id, front="Card 1", back="Back 1", deck_name="Bio")
        c2 = await service.add_card(user_id=user_id, front="Card 2", back="Back 2", deck_name="Bio")
        c3 = await service.add_card(user_id=user_id, front="Card 3", back="Back 3", deck_name="Bio")

        # Grade c1 so it is scheduled 1 day in the future
        await service.grade_card(user_id=user_id, card_id=c1.id, rating="good")

        # Next due card should be c2 or c3 (due now)
        next_card = await service.get_next_due(user_id=user_id, deck_name="Bio")
        assert next_card is not None
        assert next_card.id in (c2.id, c3.id)

        # list_due should report 2 cards currently due
        due_summary = await service.list_due(user_id=user_id, deck_name="Bio")
        assert due_summary.total_due == 2
        assert len(due_summary.cards) == 2
        due_ids = {c.id for c in due_summary.cards}
        assert c1.id not in due_ids
        assert c2.id in due_ids
        assert c3.id in due_ids
    finally:
        await engine.dispose()
