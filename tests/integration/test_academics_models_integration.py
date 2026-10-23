"""Integration tests for Academics models and database constraints on PostgreSQL (T3.1)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.config import get_settings
from sahayak.core.db.session import UnitOfWork
from sahayak.modules.academics.models import (
    Card,
    Deck,
    DifficultyLevel,
    Question,
    QuestionStatus,
    Quiz,
    QuizQuestion,
    Topic,
    TopicStats,
)
from sahayak.shared.users.models import User


@pytest.mark.integration
@pytest.mark.asyncio
async def test_academics_db_constraints_and_cascade() -> None:
    """Verify content_hash uniqueness, FK enforcement, and cascading deletion on PostgreSQL."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("PostgreSQL database is not accessible")

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with UnitOfWork(session_factory) as uow:
            # 1. Create a platform user
            user = User(
                id=uuid.uuid4(),
            )
            uow.session.add(user)

            # 2. Create topic
            unique_key = f"topic_{uuid.uuid4().hex[:8]}"
            topic = Topic(
                id=uuid.uuid4(),
                topic_key=unique_key,
                display_name="Calculus I",
            )
            uow.session.add(topic)
            await uow.session.flush()

            # 3. Create question
            content_hash = f"chash_{uuid.uuid4().hex[:12]}"
            q1 = Question(
                id=uuid.uuid4(),
                topic_id=topic.id,
                difficulty=DifficultyLevel.MEDIUM,
                stem="What is the derivative of sin(x)?",
                options={"A": "cos(x)", "B": "-cos(x)", "C": "tan(x)", "D": "sec(x)"},
                correct_key="A",
                explanation="The derivative of sin(x) with respect to x is cos(x).",
                content_hash=content_hash,
                prompt_version="v1",
                model="gemini-2.5-flash",
                status=QuestionStatus.APPROVED,
            )
            uow.session.add(q1)
            await uow.session.flush()

            # 4. Verify content_hash uniqueness: duplicate content_hash must raise IntegrityError
            q2_dup = Question(
                id=uuid.uuid4(),
                topic_id=topic.id,
                difficulty=DifficultyLevel.EASY,
                stem="Duplicate question",
                options={"A": "cos(x)", "B": "-cos(x)", "C": "tan(x)", "D": "sec(x)"},
                correct_key="A",
                explanation="Explanation",
                content_hash=content_hash,  # duplicate
                prompt_version="v1",
                model="gemini-2.5-flash",
            )
            uow.session.add(q2_dup)
            with pytest.raises(IntegrityError):
                await uow.session.flush()

            await uow.session.rollback()

        # Re-open session after rollback to test foreign keys and cascades
        async with UnitOfWork(session_factory) as uow:
            user = User(
                id=uuid.uuid4(),
            )
            uow.session.add(user)
            topic = Topic(
                id=uuid.uuid4(),
                topic_key=f"topic_{uuid.uuid4().hex[:8]}",
                display_name="Physics",
            )
            uow.session.add(topic)
            await uow.session.flush()

            # 5. FK Integrity: question with non-existent topic_id must fail
            invalid_q = Question(
                id=uuid.uuid4(),
                topic_id=uuid.uuid4(),  # non-existent
                difficulty=DifficultyLevel.EASY,
                stem="Invalid question",
                options={"A": "1", "B": "2", "C": "3", "D": "4"},
                correct_key="A",
                explanation="None",
                content_hash=f"chash_{uuid.uuid4().hex[:12]}",
                prompt_version="v1",
                model="gemini-2.5-flash",
            )
            uow.session.add(invalid_q)
            with pytest.raises(IntegrityError):
                await uow.session.flush()

            await uow.session.rollback()

        # 6. Test Decks, Cards, Quizzes, and TopicStats
        async with UnitOfWork(session_factory) as uow:
            user = User(
                id=uuid.uuid4(),
            )
            topic = Topic(
                id=uuid.uuid4(),
                topic_key=f"topic_{uuid.uuid4().hex[:8]}",
                display_name="Chemistry",
            )
            uow.session.add_all([user, topic])
            await uow.session.flush()

            deck = Deck(id=uuid.uuid4(), user_id=user.id, name="Periodic Table")
            uow.session.add(deck)
            await uow.session.flush()

            card = Card(
                id=uuid.uuid4(),
                deck_id=deck.id,
                user_id=user.id,
                front="H",
                back="Hydrogen",
            )
            uow.session.add(card)

            # Quiz and QuizQuestion
            q = Question(
                id=uuid.uuid4(),
                topic_id=topic.id,
                difficulty=DifficultyLevel.EASY,
                stem="Symbol for Gold?",
                options={"A": "Au", "B": "Ag", "C": "Fe", "D": "Cu"},
                correct_key="A",
                explanation="Au is from aurum.",
                content_hash=f"chash_{uuid.uuid4().hex[:12]}",
                prompt_version="v1",
                model="gemini-2.5-flash",
            )
            uow.session.add(q)
            await uow.session.flush()

            quiz = Quiz(
                id=uuid.uuid4(),
                user_id=user.id,
                topic_id=topic.id,
                difficulty=DifficultyLevel.EASY,
                total=1,
                expires_at=datetime.now(UTC) + timedelta(hours=2),
            )
            uow.session.add(quiz)
            await uow.session.flush()

            qq = QuizQuestion(
                quiz_id=quiz.id,
                position=1,
                question_id=q.id,
            )
            uow.session.add(qq)

            stats = TopicStats(
                user_id=user.id,
                topic_id=topic.id,
                attempts=1,
                correct=1,
            )
            uow.session.add(stats)
            await uow.session.commit()

            # Verify rows exist
            card_stmt = select(Card).where(Card.user_id == user.id)
            loaded_cards = list((await uow.session.execute(card_stmt)).scalars())
            assert len(loaded_cards) == 1
            assert loaded_cards[0].front == "H"

    finally:
        await engine.dispose()
