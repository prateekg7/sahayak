"""Unit tests for Academics background jobs: bank expansion, prefetch, and quiz expiry (T3.8)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import fakeredis.aioredis
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.cache import Cache
from sahayak.core.config import get_settings
from sahayak.core.db.session import UnitOfWork
from sahayak.modules.academics.adapters.generation import (
    QuestionGenerationPipeline,
    RawQuestionItem,
    RawQuizGenerationOutput,
)
from sahayak.modules.academics.adapters.question_bank import SQLAlchemyQuestionBank
from sahayak.modules.academics.jobs import (
    expand_bank,
    expire_quizzes,
    get_adjacent_difficulties,
    popular_topics_pregen,
    prefetch_adjacent_difficulty,
)
from sahayak.modules.academics.models import (
    DifficultyLevel,
    Question,
    Quiz,
    QuizStatus,
)
from sahayak.modules.academics.module import AcademicsModule
from sahayak.modules.academics.service.quiz import QuizService
from sahayak.shared.llm.fake import FakeLLMClient
from sahayak.shared.users.models import User  # noqa: F401
from sahayak.worker import WorkerRegistry


@pytest.fixture
def fake_clock() -> datetime:
    return datetime(2026, 10, 23, 14, 0, 0, tzinfo=UTC)


def make_sample_canned_json(count: int = 5, prefix: str | None = None) -> list[dict[str, Any]]:
    pfx = prefix or uuid.uuid4().hex[:6]
    items = [
        RawQuestionItem(
            stem=f"What is {pfx} question {i}?",
            options={
                "A": f"Option A {i}",
                "B": f"Option B {i}",
                "C": f"Option C {i}",
                "D": f"Option D {i}",
            },
            correct_key="A",
            explanation=f"Explanation for question {i}.",
        )
        for i in range(count)
    ]
    return [json.loads(RawQuizGenerationOutput(questions=items).model_dump_json())]


@pytest.mark.asyncio
async def test_expand_bank_fills_bank_and_enables_cache_hit(fake_clock: datetime) -> None:
    """Worker fills bank on miss, ensuring next quiz_start is a cache hit."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    pfx = uuid.uuid4().hex[:8]
    topic_key = f"quantum-{pfx}"
    canonical_key = topic_key
    llm = FakeLLMClient(canned_json=make_sample_canned_json(5, prefix=pfx))
    pipeline = QuestionGenerationPipeline(llm_client=llm)

    ctx: dict[str, Any] = {
        "session_factory": session_factory,
        "generator": pipeline,
    }

    try:
        # 1. Expand bank
        res = await expand_bank(
            ctx=ctx,
            topic_key=topic_key,
            difficulty="medium",
            count=5,
            threshold=5,
        )
        assert res["status"] == "success"
        assert res["generated"] == 5
        assert res["inserted"] == 5

        # 2. Verify questions are now present in bank
        async with UnitOfWork(session_factory) as uow:
            bank = SQLAlchemyQuestionBank(uow.session)
            count = await bank.count_available(canonical_key, DifficultyLevel.MEDIUM)
            assert count == 5

        # 3. Subsequent quiz_start should be a cache hit (no generator invocation)
        service = QuizService(
            session_factory=session_factory,
            generator=None,  # No generator: proves cache hit
            clock=lambda: fake_clock,
        )
        quiz_info = await service.start_quiz(
            user_id=None,
            topic=topic_key,
            difficulty="medium",
            num_questions=5,
        )
        assert quiz_info.total_questions == 5
        assert quiz_info.current_number == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_expand_bank_duplicate_triggers_produce_one_generation() -> None:
    """Duplicate triggers skip generation when distributed lock is held."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    cache = Cache(redis)

    pfx = uuid.uuid4().hex[:8]
    topic_key = f"optics-{pfx}"
    canonical_key = topic_key

    llm = FakeLLMClient(canned_json=make_sample_canned_json(5, prefix=pfx))
    pipeline = QuestionGenerationPipeline(llm_client=llm)

    ctx: dict[str, Any] = {
        "session_factory": session_factory,
        "generator": pipeline,
        "cache": cache,
    }

    try:
        # Pre-acquire the lock to simulate a concurrent running job
        lock_name = f"academics:expand_bank:{canonical_key}:medium"
        async with cache.lock(lock_name, ttl_seconds=60) as acquired:
            assert acquired is True

            # Attempt duplicate expand_bank while lock is held
            res = await expand_bank(
                ctx=ctx,
                topic_key=topic_key,
                difficulty="medium",
                count=5,
                threshold=5,
            )
            assert res["status"] == "skipped"
            assert res["reason"] == "lock_held"
            assert len(llm.history) == 0

        # After lock is released, expand_bank proceeds
        res_after = await expand_bank(
            ctx=ctx,
            topic_key=topic_key,
            difficulty="medium",
            count=5,
            threshold=5,
        )
        assert res_after["status"] == "success"
        assert res_after["generated"] == 5
        assert len(llm.history) == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_expand_bank_skips_when_sufficient_questions_exist() -> None:
    """Job skips generation when bank already meets threshold."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    topic_key = f"mechanics-{uuid.uuid4().hex[:8]}"

    try:
        async with UnitOfWork(session_factory) as uow:
            bank = SQLAlchemyQuestionBank(uow.session)
            topic = await bank.get_or_create_topic(topic_key, "Mechanics")
            questions = [
                Question(
                    topic_id=topic.id,
                    difficulty=DifficultyLevel.HARD,
                    stem=f"Mechanics question {i}?",
                    options={"A": "1", "B": "2", "C": "3", "D": "4"},
                    correct_key="A",
                    explanation="Force equation",
                    content_hash=f"mech_{uuid.uuid4().hex[:12]}",
                    prompt_version="v1",
                    model="test",
                )
                for i in range(10)
            ]
            await bank.insert_questions(questions)

        ctx: dict[str, Any] = {
            "session_factory": session_factory,
            "generator": None,  # Will not be called
        }

        res = await expand_bank(
            ctx=ctx,
            topic_key=topic_key,
            difficulty="hard",
            count=5,
            threshold=10,
        )
        assert res["status"] == "skipped"
        assert res["reason"] == "sufficient_questions"
        assert res["count"] == 10
    finally:
        await engine.dispose()


def test_get_adjacent_difficulties() -> None:
    """Check adjacent tier mappings."""
    assert get_adjacent_difficulties("easy") == ["medium"]
    assert get_adjacent_difficulties("medium") == ["easy", "hard"]
    assert get_adjacent_difficulties("hard") == ["medium"]
    assert get_adjacent_difficulties(DifficultyLevel.MEDIUM) == ["easy", "hard"]


@pytest.mark.asyncio
async def test_prefetch_adjacent_difficulty() -> None:
    """Prefetch enqueues adjacent tiers when bank count is low."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    enqueued_jobs: list[tuple[str, str, str]] = []

    async def fake_enqueuer(job_name: str, topic: str, difficulty: str) -> None:
        enqueued_jobs.append((job_name, topic, difficulty))

    topic_key = f"biology_{uuid.uuid4().hex[:8]}"
    ctx: dict[str, Any] = {
        "session_factory": session_factory,
        "enqueuer": fake_enqueuer,
    }

    try:
        res = await prefetch_adjacent_difficulty(
            ctx=ctx,
            topic_key=topic_key,
            current_difficulty="medium",
            threshold=5,
        )
        assert res["status"] == "success"
        assert res["prefetched"] == ["easy", "hard"]
        assert len(enqueued_jobs) == 2
        assert ("academics_expand_bank", topic_key, "easy") in enqueued_jobs
        assert ("academics_expand_bank", topic_key, "hard") in enqueued_jobs
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_expire_quizzes_cron(fake_clock: datetime) -> None:
    """Periodic cron marks stale in-progress quizzes as EXPIRED."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with UnitOfWork(session_factory) as uow:
            bank = SQLAlchemyQuestionBank(uow.session)
            topic = await bank.get_or_create_topic("chem", "Chemistry")

            # 1. Expired quiz (expires_at in past)
            expired_quiz = Quiz(
                topic_id=topic.id,
                difficulty=DifficultyLevel.MEDIUM,
                total=5,
                current_index=1,
                status=QuizStatus.IN_PROGRESS,
                score_correct=1,
                created_at=fake_clock - timedelta(hours=3),
                expires_at=fake_clock - timedelta(hours=1),
            )
            # 2. Active quiz (expires_at in future)
            active_quiz = Quiz(
                topic_id=topic.id,
                difficulty=DifficultyLevel.MEDIUM,
                total=5,
                current_index=0,
                status=QuizStatus.IN_PROGRESS,
                score_correct=0,
                created_at=fake_clock,
                expires_at=fake_clock + timedelta(hours=2),
            )
            uow.session.add(expired_quiz)
            uow.session.add(active_quiz)
            await uow.session.flush()
            expired_id = expired_quiz.id
            active_id = active_quiz.id

        ctx: dict[str, Any] = {
            "session_factory": session_factory,
            "clock": lambda: fake_clock,
        }

        res = await expire_quizzes(ctx)
        assert res["status"] == "success"
        assert res["expired_count"] >= 1

        async with UnitOfWork(session_factory) as uow:
            q_exp = await uow.session.get(Quiz, expired_id)
            q_act = await uow.session.get(Quiz, active_id)
            assert q_exp is not None and q_exp.status == QuizStatus.EXPIRED
            assert q_act is not None and q_act.status == QuizStatus.IN_PROGRESS
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_popular_topics_pregen(fake_clock: datetime) -> None:
    """Pregen cron generates questions across popular topic lists."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    llm = FakeLLMClient(canned_json=make_sample_canned_json(5))
    pipeline = QuestionGenerationPipeline(llm_client=llm)

    test_topic = f"pop_{uuid.uuid4().hex[:6]}"
    ctx: dict[str, Any] = {
        "session_factory": session_factory,
        "generator": pipeline,
    }

    try:
        res = await popular_topics_pregen(
            ctx=ctx,
            topics=[test_topic],
            difficulties=("medium",),
        )
        assert res["status"] == "success"
        assert res["topics_checked"] == 1
        assert len(res["details"]) == 1
        assert res["details"][0]["status"] == "success"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_quiz_start_triggers_background_expansion_on_miss(fake_clock: datetime) -> None:
    """Starting a quiz on a cache miss triggers the background expansion and prefetch enqueuer."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    pfx = uuid.uuid4().hex[:8]
    topic_key = f"miss-{pfx}"
    canonical_key = topic_key
    llm = FakeLLMClient(canned_json=make_sample_canned_json(5, prefix=pfx))
    pipeline = QuestionGenerationPipeline(llm_client=llm)

    enqueued_jobs: list[tuple[str, str, str]] = []

    async def spy_enqueuer(job_name: str, topic: str, difficulty: str) -> None:
        enqueued_jobs.append((job_name, topic, difficulty))

    service = QuizService(
        session_factory=session_factory,
        generator=pipeline,
        clock=lambda: fake_clock,
        enqueuer=spy_enqueuer,
        bank_min_threshold=10,
    )

    try:
        await service.start_quiz(
            user_id=None,
            topic=topic_key,
            difficulty="medium",
            num_questions=5,
        )
        assert ("academics_expand_bank", canonical_key, "medium") in enqueued_jobs
        assert ("academics_prefetch_adjacent", canonical_key, "medium") in enqueued_jobs
    finally:
        await engine.dispose()


def test_academics_module_registers_jobs() -> None:
    """AcademicsModule properly registers worker jobs and cron jobs."""
    registry = WorkerRegistry()
    module = AcademicsModule()
    module.register_jobs(registry)

    func_names = [getattr(f, "name", getattr(f, "__name__", "")) for f in registry.get_functions()]
    cron_names = [c.name for c in registry.get_cron_jobs()]

    assert "academics_expand_bank" in func_names
    assert "academics_prefetch_adjacent" in func_names
    assert "academics_expire_quizzes" in cron_names
    assert "academics_popular_topics_pregen" in cron_names
