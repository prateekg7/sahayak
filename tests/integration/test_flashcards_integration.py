"""Integration tests for flashcards persistence and SM-2 scheduling (T3.9)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.config import get_settings
from sahayak.core.db.session import UnitOfWork
from sahayak.modules.academics.service.flashcards import FlashcardService
from sahayak.shared.srs.sm2 import ReviewRating
from sahayak.shared.users.models import User


@pytest.mark.integration
@pytest.mark.asyncio
async def test_flashcard_persistence_and_due_queries() -> None:
    """Test deck creation, card persistence, SM-2 grading and due queries on real PostgreSQL."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("PostgreSQL database is not accessible")

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        now = datetime(2026, 10, 23, 12, 0, 0, tzinfo=UTC)

        # 1. Create test user
        user = User()
        async with UnitOfWork(session_factory) as uow:
            uow.session.add(user)

        service = FlashcardService(session_factory=session_factory, clock=lambda: now)

        # 2. Add cards across two decks
        card1 = await service.add_card(
            user_id=user.id,
            deck_name="Biology",
            front="What is ATP?",
            back="Adenosine Triphosphate",
        )
        card2 = await service.add_card(
            user_id=user.id,
            deck_name="Biology",
            front="Where does glycolysis occur?",
            back="Cytoplasm",
        )
        _ = await service.add_card(
            user_id=user.id,
            deck_name="Chemistry",
            front="What is Avogadro's number?",
            back="6.022 x 10^23",
        )

        # 3. Verify counts
        due_info_all = await service.list_due(user.id)
        assert due_info_all.total_due == 3

        due_info_bio = await service.list_due(user.id, deck_name="Biology")
        assert due_info_bio.total_due == 2

        # 4. Review next due
        next_card = await service.get_next_due(user.id, deck_name="Biology")
        assert next_card is not None
        assert next_card.id in (card1.id, card2.id)

        # 5. Grade card1 as 'good'
        graded1 = await service.grade_card(
            user_id=user.id,
            card_id=card1.id,
            rating=ReviewRating.GOOD.value,
        )
        assert graded1.repetitions == 1
        assert graded1.interval_days == 1
        assert graded1.due_at == now + timedelta(days=1)

        # 6. Verify count of currently due cards decreases
        due_now = await service.list_due(user.id, deck_name="Biology")
        assert due_now.total_due == 1
    finally:
        await engine.dispose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_due_card_query_uses_index_explain() -> None:
    """Assert that due card queries use the (user_id, due_at) index in PostgreSQL EXPLAIN plan."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("PostgreSQL database is not accessible")

    try:
        async with engine.connect() as conn:
            # We run an EXPLAIN on the core due-card query
            # We temporarily set enable_seqscan = off to verify the query planner index choice
            # in test environments with small row counts
            await conn.execute(text("SET LOCAL enable_seqscan = off"))
            dummy_uid = uuid.uuid4()
            now_str = datetime.now(UTC).isoformat()

            query = text(
                f"""
                EXPLAIN
                SELECT id, user_id, deck_id, front, back, ease, interval_days, repetitions, due_at
                FROM academics.cards
                WHERE user_id = '{dummy_uid}' AND due_at <= '{now_str}'
                ORDER BY due_at ASC
                LIMIT 1;
                """
            )
            result = await conn.execute(query)
            plan_lines = [row[0] for row in result.fetchall()]
            plan_text = "\n".join(plan_lines)

            # Assert that the index on (user_id, due_at) is selected
            assert "ix_academics_cards_user_due" in plan_text, (
                f"Expected index 'ix_academics_cards_user_due' in EXPLAIN plan, got:\n{plan_text}"
            )
    finally:
        await engine.dispose()
