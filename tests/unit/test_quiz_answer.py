"""Unit tests for quiz answer evaluation and turn progression (T3.7)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.config import get_settings
from sahayak.core.db.session import UnitOfWork
from sahayak.core.errors import ForbiddenError, InvalidInputError, NotFoundError
from sahayak.core.events import OutboxEventRecord
from sahayak.modules.academics.adapters.generation import (
    QuestionGenerationPipeline,
    RawQuestionItem,
    RawQuizGenerationOutput,
)
from sahayak.modules.academics.models import Quiz, QuizStatus, TopicStats
from sahayak.modules.academics.service.quiz import QuizService
from sahayak.shared.llm.fake import FakeLLMClient
from sahayak.shared.users.models import User


@pytest.fixture
def fake_clock() -> datetime:
    """Deterministic timestamp for quiz lifecycle tests."""
    return datetime(2026, 10, 23, 15, 0, tzinfo=UTC)


async def _setup_quiz_with_3_questions(
    service: QuizService,
    session_factory: async_sessionmaker[Any],
    user_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Helper to start a fresh 3-question quiz."""
    if user_id is not None:
        async with UnitOfWork(session_factory) as uow:
            uow.session.add(User(id=user_id))
            await uow.session.commit()

    test_id = uuid.uuid4().hex[:6]
    started = await service.start_quiz(
        user_id=user_id,
        topic=f"Cellular Respiration {test_id}",
        difficulty="medium",
        num_questions=3,
    )
    return started.quiz_id


@pytest.mark.asyncio
async def test_quiz_answer_correct_intermediate_question(fake_clock: datetime) -> None:
    """Answering correctly on intermediate question increments score and returns next question."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    test_id = uuid.uuid4().hex[:6]
    canned = RawQuizGenerationOutput(
        questions=[
            RawQuestionItem(
                stem=f"Cellular bio {test_id} question {i}?",
                options={"A": "Mitochondria", "B": "Ribosome", "C": "Nucleus", "D": "Vacuole"},
                correct_key="A",
                explanation=f"Organelle explanation {i}.",
            )
            for i in range(5)
        ]
    )
    fake_llm = FakeLLMClient(canned_json=[json.loads(canned.model_dump_json())])
    generator = QuestionGenerationPipeline(llm_client=fake_llm)

    try:
        service = QuizService(
            session_factory=session_factory,
            generator=generator,
            clock=lambda: fake_clock,
        )

        quiz_id = await _setup_quiz_with_3_questions(service, session_factory)

        # Question 1: Answer with correct text
        ans = await service.answer_question(
            user_id=None,
            quiz_id=quiz_id,
            answer_text="Mitochondria",
        )

        assert ans.correct is True
        assert ans.score_correct == 1
        assert ans.score_answered == 1
        assert ans.score_total == 3
        assert ans.finished is False
        assert ans.next_number == 2
        assert ans.next_question is not None
        assert "Question 2" in ans.spoken_summary
        assert "That's correct!" in ans.spoken_summary

    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_quiz_answer_incorrect_intermediate_question(fake_clock: datetime) -> None:
    """Answering incorrectly states correct answer and advances to next question."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    test_id = uuid.uuid4().hex[:6]
    canned = RawQuizGenerationOutput(
        questions=[
            RawQuestionItem(
                stem=f"Cellular bio {test_id} question {i}?",
                options={"A": "Mitochondria", "B": "Ribosome", "C": "Nucleus", "D": "Vacuole"},
                correct_key="A",
                explanation=f"Organelle explanation {i}.",
            )
            for i in range(5)
        ]
    )
    fake_llm = FakeLLMClient(canned_json=[json.loads(canned.model_dump_json())])
    generator = QuestionGenerationPipeline(llm_client=fake_llm)

    try:
        service = QuizService(
            session_factory=session_factory,
            generator=generator,
            clock=lambda: fake_clock,
        )

        quiz_id = await _setup_quiz_with_3_questions(service, session_factory)

        # In Question 1, correct is whatever was mapped to Mitochondria
        # Answering "vacuole" is incorrect
        ans = await service.answer_question(
            user_id=None,
            quiz_id=quiz_id,
            answer_text="Vacuole",
        )

        assert ans.correct is False
        assert ans.score_correct == 0
        assert ans.score_answered == 1
        assert ans.finished is False
        assert ans.next_number == 2
        assert "Not quite" in ans.spoken_summary

    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_quiz_answer_ambiguous_does_not_consume_attempt(fake_clock: datetime) -> None:
    """Ambiguous answer raises InvalidInputError without consuming the attempt."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    test_id = uuid.uuid4().hex[:6]
    canned = RawQuizGenerationOutput(
        questions=[
            RawQuestionItem(
                stem=f"Cellular bio {test_id} question {i}?",
                options={"A": "Mitochondria", "B": "Ribosome", "C": "Nucleus", "D": "Vacuole"},
                correct_key="A",
                explanation=f"Organelle explanation {i}.",
            )
            for i in range(5)
        ]
    )
    fake_llm = FakeLLMClient(canned_json=[json.loads(canned.model_dump_json())])
    generator = QuestionGenerationPipeline(llm_client=fake_llm)

    try:
        service = QuizService(
            session_factory=session_factory,
            generator=generator,
            clock=lambda: fake_clock,
        )

        quiz_id = await _setup_quiz_with_3_questions(service, session_factory)

        # Ambiguous response
        with pytest.raises(InvalidInputError) as exc_info:
            await service.answer_question(
                user_id=None,
                quiz_id=quiz_id,
                answer_text="A or B",
            )
        assert "I'm not sure which option you meant" in str(exc_info.value)

        # Verify question 1 is still active and index is still 0
        async with UnitOfWork(session_factory) as uow:
            quiz = await uow.session.get(Quiz, quiz_id)
            assert quiz is not None
            assert quiz.current_index == 0
            assert quiz.score_correct == 0

    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_quiz_answer_completion_and_event_publishing(fake_clock: datetime) -> None:
    """Answering the final question marks quiz COMPLETED and emits domain event."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    test_id = uuid.uuid4().hex[:6]
    canned = RawQuizGenerationOutput(
        questions=[
            RawQuestionItem(
                stem=f"Cellular bio {test_id} question {i}?",
                options={"A": "Mitochondria", "B": "Ribosome", "C": "Nucleus", "D": "Vacuole"},
                correct_key="A",
                explanation=f"Organelle explanation {i}.",
            )
            for i in range(5)
        ]
    )
    fake_llm = FakeLLMClient(canned_json=[json.loads(canned.model_dump_json())])
    generator = QuestionGenerationPipeline(llm_client=fake_llm)

    user_id = uuid.uuid4()

    try:
        service = QuizService(
            session_factory=session_factory,
            generator=generator,
            clock=lambda: fake_clock,
        )

        quiz_id = await _setup_quiz_with_3_questions(service, session_factory, user_id=user_id)

        # Answer Q1
        await service.answer_question(user_id=user_id, quiz_id=quiz_id, answer_text="Mitochondria")
        # Answer Q2
        await service.answer_question(user_id=user_id, quiz_id=quiz_id, answer_text="Ribosome")
        # Answer Q3 (final)
        ans3 = await service.answer_question(
            user_id=user_id, quiz_id=quiz_id, answer_text="Mitochondria"
        )

        assert ans3.finished is True
        assert ans3.next_number is None
        assert ans3.next_question is None
        assert "You finished the quiz" in ans3.spoken_summary

        # Check DB state and outbox event
        async with UnitOfWork(session_factory) as uow:
            quiz = await uow.session.get(Quiz, quiz_id)
            assert quiz is not None
            assert quiz.status == QuizStatus.COMPLETED
            assert quiz.finished_at is not None

            # Outbox event emitted
            event_stmt = select(OutboxEventRecord).where(
                OutboxEventRecord.type == "academics.quiz.finished"
            )
            res = await uow.session.execute(event_stmt)
            events = res.scalars().all()
            matching = [e for e in events if e.payload.get("quiz_id") == str(quiz_id)]
            assert len(matching) == 1
            payload = matching[0].payload
            assert payload["user_id"] == str(user_id)
            assert payload["total_questions"] == 3
            assert payload["score"] >= 1

            # TopicStats updated
            stats_stmt = select(TopicStats).where(
                TopicStats.user_id == user_id,
                TopicStats.topic_id == quiz.topic_id,
            )
            stats_res = await uow.session.execute(stats_stmt)
            stats = stats_res.scalar_one_or_none()
            assert stats is not None
            assert stats.attempts == 3

    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_quiz_answer_expired_quiz_raises_not_found(fake_clock: datetime) -> None:
    """Answering an expired quiz marks it EXPIRED and raises NotFoundError."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    test_id = uuid.uuid4().hex[:6]
    canned = RawQuizGenerationOutput(
        questions=[
            RawQuestionItem(
                stem=f"Cellular bio {test_id} question {i}?",
                options={"A": "Mitochondria", "B": "Ribosome", "C": "Nucleus", "D": "Vacuole"},
                correct_key="A",
                explanation=f"Organelle explanation {i}.",
            )
            for i in range(5)
        ]
    )
    fake_llm = FakeLLMClient(canned_json=[json.loads(canned.model_dump_json())])
    generator = QuestionGenerationPipeline(llm_client=fake_llm)

    current_time = fake_clock

    try:
        service = QuizService(
            session_factory=session_factory,
            generator=generator,
            clock=lambda: current_time,
            quiz_ttl_minutes=15,
        )

        quiz_id = await _setup_quiz_with_3_questions(service, session_factory)

        # Fast-forward clock past TTL
        current_time = fake_clock + timedelta(minutes=20)

        with pytest.raises(NotFoundError):
            await service.answer_question(
                user_id=None,
                quiz_id=quiz_id,
                answer_text="A",
            )

    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_quiz_answer_cross_user_forbidden(fake_clock: datetime) -> None:
    """User B cannot answer a quiz owned by User A."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    test_id = uuid.uuid4().hex[:6]
    canned = RawQuizGenerationOutput(
        questions=[
            RawQuestionItem(
                stem=f"Cellular bio {test_id} question {i}?",
                options={"A": "Mitochondria", "B": "Ribosome", "C": "Nucleus", "D": "Vacuole"},
                correct_key="A",
                explanation=f"Organelle explanation {i}.",
            )
            for i in range(5)
        ]
    )
    fake_llm = FakeLLMClient(canned_json=[json.loads(canned.model_dump_json())])
    generator = QuestionGenerationPipeline(llm_client=fake_llm)

    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    try:
        async with UnitOfWork(session_factory) as uow:
            uow.session.add(User(id=user_b))
            await uow.session.commit()

        service = QuizService(
            session_factory=session_factory,
            generator=generator,
            clock=lambda: fake_clock,
        )

        quiz_id = await _setup_quiz_with_3_questions(service, session_factory, user_id=user_a)

        with pytest.raises(ForbiddenError):
            await service.answer_question(
                user_id=user_b,
                quiz_id=quiz_id,
                answer_text="A",
            )

    finally:
        await engine.dispose()
