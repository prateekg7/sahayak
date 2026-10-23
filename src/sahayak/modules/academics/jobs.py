"""Background jobs for bank expansion, difficulty prefetching, and quiz expiration."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any, cast

import structlog
from sqlalchemy import update
from sqlalchemy.engine import CursorResult

from sahayak.core.cache import Cache
from sahayak.core.config import get_settings
from sahayak.core.db.session import SessionFactory, UnitOfWork
from sahayak.modules.academics.adapters.generation import QuestionGenerationPipeline
from sahayak.modules.academics.adapters.question_bank import SQLAlchemyQuestionBank
from sahayak.modules.academics.domain.topics import normalize_topic
from sahayak.modules.academics.models import (
    DifficultyLevel,
    Quiz,
    QuizStatus,
)

logger = structlog.get_logger(__name__)

EXPAND_BANK_LOCK_TTL_SECONDS = 60
DEFAULT_BATCH_COUNT = 5
DEFAULT_BANK_THRESHOLD = 10


def _resolve_cache(ctx: dict[str, Any]) -> Cache | None:
    """Extract Cache instance from arq context or construct from redis connection."""
    cache = ctx.get("cache")
    if isinstance(cache, Cache):
        return cache
    redis_client = ctx.get("redis")
    if redis_client is not None:
        return Cache(redis_client, namespace="sahayak")
    return None


def _resolve_session_factory(ctx: dict[str, Any]) -> SessionFactory | None:
    """Extract SessionFactory from arq context or module dependencies."""
    sf = ctx.get("session_factory")
    if sf is not None:
        return sf  # type: ignore[no-any-return]
    return None


def _resolve_generator(ctx: dict[str, Any]) -> QuestionGenerationPipeline | None:
    """Extract or construct QuestionGenerationPipeline from arq context."""
    gen = ctx.get("generator")
    if isinstance(gen, QuestionGenerationPipeline):
        return gen

    llm_client = ctx.get("llm_client")
    if llm_client is not None:
        from sahayak.modules.academics.adapters.verification import QuestionVerifier

        verifier = QuestionVerifier(llm_client=llm_client)
        return QuestionGenerationPipeline(llm_client=llm_client, verifier=verifier)

    return None


async def expand_bank(
    ctx: dict[str, Any],
    topic_key: str,
    difficulty: str = "medium",
    count: int = DEFAULT_BATCH_COUNT,
    threshold: int = DEFAULT_BANK_THRESHOLD,
) -> dict[str, Any]:
    """Expand question bank for topic and difficulty if available questions are below threshold.

    Uses a distributed Redis lock to prevent concurrent duplicate generation.
    """
    # 1. Parse difficulty enum
    try:
        diff_enum = DifficultyLevel(difficulty.lower().strip())
    except ValueError:
        diff_enum = DifficultyLevel.MEDIUM

    norm_key, _ = normalize_topic(topic_key)
    cache = _resolve_cache(ctx)

    # 2. Acquire distributed lock if cache/redis is available
    if cache is not None:
        lock_name = f"academics:expand_bank:{norm_key}:{diff_enum.value}"
        async with cache.lock(lock_name, ttl_seconds=EXPAND_BANK_LOCK_TTL_SECONDS) as acquired:
            if not acquired:
                logger.info(
                    "expand_bank_skipped_lock_held",
                    topic_key=norm_key,
                    difficulty=diff_enum.value,
                )
                return {
                    "status": "skipped",
                    "reason": "lock_held",
                    "topic_key": norm_key,
                    "difficulty": diff_enum.value,
                }
            return await _do_expand_bank(
                ctx=ctx,
                topic_key=norm_key,
                diff_enum=diff_enum,
                count=count,
                threshold=threshold,
            )

    return await _do_expand_bank(
        ctx=ctx,
        topic_key=norm_key,
        diff_enum=diff_enum,
        count=count,
        threshold=threshold,
    )


async def _do_expand_bank(
    ctx: dict[str, Any],
    topic_key: str,
    diff_enum: DifficultyLevel,
    count: int,
    threshold: int,
) -> dict[str, Any]:
    """Execute the bank count check and generation under lock."""
    session_factory = _resolve_session_factory(ctx)
    if session_factory is None:
        logger.error("expand_bank_missing_session_factory", topic_key=topic_key)
        return {"status": "error", "reason": "session_factory_missing"}

    async with UnitOfWork(session_factory) as uow:
        bank = SQLAlchemyQuestionBank(uow.session)
        current_count = await bank.count_available(topic_key, diff_enum)
        if current_count >= threshold:
            logger.info(
                "expand_bank_skipped_sufficient_questions",
                topic_key=topic_key,
                difficulty=diff_enum.value,
                count=current_count,
            )
            return {
                "status": "skipped",
                "reason": "sufficient_questions",
                "topic_key": topic_key,
                "difficulty": diff_enum.value,
                "count": current_count,
            }

        topic_entity = await bank.find_topic(topic_key)
        if topic_entity is None:
            _, display_name = normalize_topic(topic_key)
            topic_entity = await bank.get_or_create_topic(topic_key, display_name)
        topic_id = topic_entity.id
        display_name = topic_entity.display_name

    generator = _resolve_generator(ctx)
    if generator is None:
        logger.error("expand_bank_no_generator", topic_key=topic_key)
        return {"status": "error", "reason": "no_generator_available"}

    needed = max(count, threshold - current_count)
    logger.info(
        "expand_bank_generating",
        topic_key=topic_key,
        difficulty=diff_enum.value,
        needed=needed,
    )
    gen_result = await generator.generate_questions(
        topic=display_name,
        difficulty=diff_enum,
        count=needed,
        topic_id=topic_id,
    )

    if not gen_result.questions:
        logger.warning("expand_bank_generated_no_questions", topic_key=topic_key)
        return {
            "status": "empty",
            "topic_key": topic_key,
            "difficulty": diff_enum.value,
            "generated": 0,
            "inserted": 0,
        }

    async with UnitOfWork(session_factory) as uow:
        bank = SQLAlchemyQuestionBank(uow.session)
        inserted = await bank.insert_questions(gen_result.questions)

    logger.info(
        "expand_bank_completed",
        topic_key=topic_key,
        difficulty=diff_enum.value,
        generated=len(gen_result.questions),
        inserted=len(inserted),
    )
    return {
        "status": "success",
        "topic_key": topic_key,
        "difficulty": diff_enum.value,
        "generated": len(gen_result.questions),
        "inserted": len(inserted),
    }


def get_adjacent_difficulties(difficulty: str | DifficultyLevel) -> list[str]:
    """Return adjacent difficulty names for proactive caching."""
    if isinstance(difficulty, DifficultyLevel):
        diff_val = difficulty.value
    else:
        diff_val = str(difficulty).lower().strip()

    if diff_val == "easy":
        return ["medium"]
    if diff_val == "medium":
        return ["easy", "hard"]
    if diff_val == "hard":
        return ["medium"]
    return ["medium"]


async def prefetch_adjacent_difficulty(
    ctx: dict[str, Any],
    topic_key: str,
    current_difficulty: str = "medium",
    threshold: int = 5,
) -> dict[str, Any]:
    """Proactively expand the question bank for adjacent difficulty tiers."""
    adjacents = get_adjacent_difficulties(current_difficulty)
    prefetched: list[str] = []

    session_factory = _resolve_session_factory(ctx)
    if session_factory is None:
        return {"status": "error", "reason": "session_factory_missing"}

    enqueuer = ctx.get("enqueuer")

    for adj_diff in adjacents:
        try:
            adj_enum = DifficultyLevel(adj_diff)
        except ValueError:
            continue

        async with UnitOfWork(session_factory) as uow:
            bank = SQLAlchemyQuestionBank(uow.session)
            count = await bank.count_available(topic_key, adj_enum)

        if count < threshold:
            if callable(enqueuer):
                await enqueuer("academics_expand_bank", topic_key, adj_diff)
            else:
                await expand_bank(
                    ctx,
                    topic_key=topic_key,
                    difficulty=adj_diff,
                    count=5,
                    threshold=threshold,
                )
            prefetched.append(adj_diff)

    return {
        "status": "success",
        "topic_key": topic_key,
        "prefetched": prefetched,
    }


async def expire_quizzes(
    ctx: dict[str, Any],
) -> dict[str, Any]:
    """Cron job: update expired in-progress quizzes to QuizStatus.EXPIRED."""
    session_factory = _resolve_session_factory(ctx)
    if session_factory is None:
        logger.error("expire_quizzes_missing_session_factory")
        return {"status": "error", "reason": "session_factory_missing"}

    clock: Callable[[], datetime] = ctx.get("clock") or (lambda: datetime.now(UTC))
    now = clock()

    async with UnitOfWork(session_factory) as uow:
        stmt = (
            update(Quiz)
            .where(
                Quiz.status == QuizStatus.IN_PROGRESS,
                Quiz.expires_at <= now,
            )
            .values(status=QuizStatus.EXPIRED)
        )
        res = await uow.session.execute(stmt)
        cursor_res = cast(CursorResult[Any], res)
        expired_count = int(cursor_res.rowcount or 0)

    logger.info("expire_quizzes_completed", expired_count=expired_count)
    return {"status": "success", "expired_count": expired_count}


async def popular_topics_pregen(
    ctx: dict[str, Any],
    topics: Sequence[str] | None = None,
    difficulties: Sequence[str] = ("medium", "easy"),
) -> dict[str, Any]:
    """Cron job: verify and pregenerate question pools for configured popular topics."""
    settings = get_settings()
    target_topics = list(topics) if topics is not None else list(settings.academics_popular_topics)
    threshold = settings.academics_bank_min_threshold

    results: list[dict[str, Any]] = []
    for topic_raw in target_topics:
        norm_key, _ = normalize_topic(topic_raw)
        for diff in difficulties:
            res = await expand_bank(
                ctx=ctx,
                topic_key=norm_key,
                difficulty=diff,
                count=DEFAULT_BATCH_COUNT,
                threshold=threshold,
            )
            results.append(res)

    return {
        "status": "success",
        "topics_checked": len(target_topics),
        "details": results,
    }
