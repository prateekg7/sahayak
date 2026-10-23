"""Unit tests for QuizService and quiz_start orchestration (T3.6)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.config import get_settings
from sahayak.core.db.session import UnitOfWork
from sahayak.core.errors import UpstreamUnavailableError
from sahayak.modules.academics.adapters.generation import (
    QuestionGenerationPipeline,
    RawQuestionItem,
    RawQuizGenerationOutput,
)
from sahayak.modules.academics.adapters.question_bank import SQLAlchemyQuestionBank
from sahayak.modules.academics.models import (
    DifficultyLevel,
    Question,
)
from sahayak.modules.academics.service.quiz import QuizService
from sahayak.shared.llm.fake import FakeLLMClient
from sahayak.shared.users.models import User


@pytest.fixture
def fake_clock() -> datetime:
    return datetime(2026, 10, 23, 14, 0, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_quiz_service_cache_hit_flow(fake_clock: datetime) -> None:
    """When bank already has sufficient questions, quiz starts directly without generation."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with UnitOfWork(session_factory) as uow:
            bank = SQLAlchemyQuestionBank(uow.session)
            topic = await bank.get_or_create_topic("astronomy", "Astronomy")

            # Seed 3 questions
            seeded_questions = [
                Question(
                    topic_id=topic.id,
                    difficulty=DifficultyLevel.EASY,
                    stem=f"Astronomy question {i}?",
                    options={"A": "Mercury", "B": "Venus", "C": "Mars", "D": "Jupiter"},
                    correct_key="A",
                    explanation="Solar system facts",
                    content_hash=f"astro_{uuid.uuid4().hex[:12]}",
                    prompt_version="v1",
                    model="test-model",
                )
                for i in range(3)
            ]
            await bank.insert_questions(seeded_questions)

            user = User(locale="en-US", timezone="UTC")
            uow.session.add(user)
            await uow.session.commit()
            user_id = user.id

        service = QuizService(
            session_factory=session_factory,
            generator=None,  # No generator needed on cache hit
            clock=lambda: fake_clock,
            quiz_ttl_minutes=60,
        )

        started = await service.start_quiz(
            user_id=user_id,
            topic="astronomy",
            difficulty="easy",
            num_questions=3,
        )

        assert started.topic_display_name == "Astronomy"
        assert started.difficulty == DifficultyLevel.EASY
        assert started.total_questions == 3
        assert started.current_number == 1
        assert len(started.options) == 4
        assert "Astronomy" in started.spoken_summary
        assert "Question 1" in started.spoken_summary
        # Verify no correct answer leakage
        assert not hasattr(started, "correct_key")
        assert not hasattr(started, "explanation")

    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_quiz_service_cache_miss_triggers_generator(fake_clock: datetime) -> None:
    """When bank has fewer questions than requested, generator is called synchronously."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    test_id = uuid.uuid4().hex[:6]
    unique_topic = f"Marine Biology {test_id}"

    canned_payload = RawQuizGenerationOutput(
        questions=[
            RawQuestionItem(
                stem=f"Marine biology {test_id} question {i}?",
                options={"A": "Plankton", "B": "Coral", "C": "Kelp", "D": "Whale"},
                correct_key="A",
                explanation="Marine organisms facts.",
            )
            for i in range(5)
        ]
    )
    fake_llm = FakeLLMClient(canned_json=[json.loads(canned_payload.model_dump_json())])
    generator = QuestionGenerationPipeline(llm_client=fake_llm)

    try:
        service = QuizService(
            session_factory=session_factory,
            generator=generator,
            clock=lambda: fake_clock,
        )

        started = await service.start_quiz(
            user_id=None,  # Anonymous caller
            topic=unique_topic,
            difficulty="medium",
            num_questions=3,
        )

        assert started.total_questions == 3
        assert started.current_number == 1
        assert len(started.options) == 4
        assert "Marine biology" in started.stem

    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_quiz_service_clamps_question_bounds(fake_clock: datetime) -> None:
    """num_questions is clamped to [3, 10]."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    test_id = uuid.uuid4().hex[:6]
    unique_topic = f"Quantum Physics {test_id}"

    canned_payload = RawQuizGenerationOutput(
        questions=[
            RawQuestionItem(
                stem=f"Quantum physics {test_id} question {i}?",
                options={"A": "Photon", "B": "Electron", "C": "Proton", "D": "Neutron"},
                correct_key="A",
                explanation="Quantum particle facts.",
            )
            for i in range(12)
        ]
    )
    fake_llm = FakeLLMClient(canned_json=[json.loads(canned_payload.model_dump_json())])
    generator = QuestionGenerationPipeline(llm_client=fake_llm)

    try:
        service = QuizService(
            session_factory=session_factory,
            generator=generator,
            clock=lambda: fake_clock,
        )

        # Request 1 -> clamped up to 3
        started_min = await service.start_quiz(
            user_id=None,
            topic=unique_topic,
            difficulty="easy",
            num_questions=1,
        )
        assert started_min.total_questions == 3

    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_quiz_service_raises_when_no_questions_available(fake_clock: datetime) -> None:
    """If no questions exist and generator is None or fails, raises UpstreamUnavailableError."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    empty_topic = f"Empty Topic {uuid.uuid4().hex[:6]}"

    try:
        service = QuizService(
            session_factory=session_factory,
            generator=None,  # No generator
            clock=lambda: fake_clock,
        )

        with pytest.raises(UpstreamUnavailableError):
            await service.start_quiz(
                user_id=None,
                topic=empty_topic,
                difficulty="hard",
                num_questions=3,
            )

    finally:
        await engine.dispose()
