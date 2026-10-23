"""Integration tests for SQLAlchemyQuestionBank repository (T3.2)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.config import get_settings
from sahayak.core.db.session import UnitOfWork
from sahayak.modules.academics.adapters.question_bank import SQLAlchemyQuestionBank
from sahayak.modules.academics.models import (
    DifficultyLevel,
    Question,
    QuestionStatus,
)
from sahayak.modules.academics.service.quality import QuestionQualityService


@pytest.mark.integration
@pytest.mark.asyncio
async def test_question_bank_crud_and_deduplication() -> None:
    """Test topic creation, question insertion with deduplication, and lookup."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))

    # Check connection
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("PostgreSQL database is not accessible")

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with UnitOfWork(session_factory) as uow:
            repo = SQLAlchemyQuestionBank(uow.session)

            # 1. Topic get_or_create idempotence
            t1 = await repo.get_or_create_topic("photosynthesis", "Photosynthesis")
            t2 = await repo.get_or_create_topic("photosynthesis", "Photosynthesis")
            assert t1.id == t2.id
            assert t1.topic_key == "photosynthesis"

            # 2. Insert questions with deduplication
            q1_hash = f"hash_{uuid.uuid4().hex[:12]}"
            q2_hash = f"hash_{uuid.uuid4().hex[:12]}"
            q3_hash = f"hash_{uuid.uuid4().hex[:12]}"

            q1 = Question(
                topic_id=t1.id,
                difficulty=DifficultyLevel.EASY,
                stem="What pigment absorbs light?",
                options={"A": "Chlorophyll", "B": "Hemoglobin", "C": "Melanin", "D": "Carotene"},
                correct_key="A",
                explanation="Chlorophyll absorbs red and blue light.",
                content_hash=q1_hash,
                prompt_version="v1",
                model="gemini-2.5-flash",
            )
            q2 = Question(
                topic_id=t1.id,
                difficulty=DifficultyLevel.EASY,
                stem="Where does photosynthesis take place?",
                options={"A": "Mitochondria", "B": "Chloroplast", "C": "Ribosome", "D": "Nucleus"},
                correct_key="B",
                explanation="Chloroplasts house chlorophyll.",
                content_hash=q2_hash,
                prompt_version="v1",
                model="gemini-2.5-flash",
            )
            inserted = await repo.insert_questions([q1, q2])
            assert len(inserted) == 2

            # Deduplication: attempt to insert duplicate q1 with a new q3
            q1_dup = Question(
                topic_id=t1.id,
                difficulty=DifficultyLevel.EASY,
                stem="Duplicate Q1 stem",
                options={"A": "1", "B": "2", "C": "3", "D": "4"},
                correct_key="A",
                explanation="dup",
                content_hash=q1_hash,
                prompt_version="v1",
                model="gemini-2.5-flash",
            )
            q3 = Question(
                topic_id=t1.id,
                difficulty=DifficultyLevel.EASY,
                stem="What is produced during light reactions?",
                options={"A": "ATP & NADPH", "B": "Glucose", "C": "Lactate", "D": "CO2"},
                correct_key="A",
                explanation="Light reactions produce ATP and NADPH.",
                content_hash=q3_hash,
                prompt_version="v1",
                model="gemini-2.5-flash",
            )
            batch2 = await repo.insert_questions([q1_dup, q3])
            assert len(batch2) == 2
            # Total count should be 3 (q1, q2, q3)
            total = await repo.count_available("photosynthesis", DifficultyLevel.EASY)
            assert total == 3

            # 3. Exclusion query and limits
            excluded = [q1.id]
            filtered = await repo.find_questions(
                topic_key="photosynthesis",
                difficulty=DifficultyLevel.EASY,
                exclude_ids=excluded,
                limit=5,
            )
            assert len(filtered) == 2
            filtered_ids = {q.id for q in filtered}
            assert q1.id not in filtered_ids
            assert q2.id in filtered_ids
            assert q3.id in filtered_ids

            count_excluded = await repo.count_available(
                topic_key="photosynthesis",
                difficulty=DifficultyLevel.EASY,
                exclude_ids=excluded,
            )
            assert count_excluded == 2

            # 4. Flagging and quarantine cycle
            # Flag 1
            f1 = await repo.flag_question(q1.id, quarantine_threshold=3)
            assert f1 is not None
            assert f1.flag_count == 1
            assert f1.status == QuestionStatus.FLAGGED

            # Flag 2
            f2 = await repo.flag_question(q1.id, quarantine_threshold=3)
            assert f2 is not None
            assert f2.flag_count == 2
            assert f2.status == QuestionStatus.FLAGGED

            # Flag 3 -> auto-quarantined
            f3 = await repo.flag_question(q1.id, quarantine_threshold=3)
            assert f3 is not None
            assert f3.flag_count == 3
            assert f3.status == QuestionStatus.QUARANTINED

            # Question 1 is quarantined, so count of approved is reduced
            after_quarantine_count = await repo.count_available(
                "photosynthesis", DifficultyLevel.EASY
            )
            assert after_quarantine_count == 2

            # Direct quarantine on q2
            q2_quarantine = await repo.quarantine_question(q2.id)
            assert q2_quarantine is not None
            assert q2_quarantine.status == QuestionStatus.QUARANTINED

            after_q2_count = await repo.count_available("photosynthesis", DifficultyLevel.EASY)
            assert after_q2_count == 1

            # 5. QuestionQualityService on real DB
            quality_service = QuestionQualityService(repo, quarantine_threshold=3)
            # q3 is still approved
            flagged_q3 = await quality_service.flag_question(q3.id, reason="Bad explanation")
            assert flagged_q3 is not None
            assert flagged_q3.flag_count == 1
            assert flagged_q3.status == QuestionStatus.FLAGGED

            quarantined_q3 = await quality_service.quarantine_question(
                q3.id, reason="Critical error"
            )
            assert quarantined_q3 is not None
            assert quarantined_q3.status == QuestionStatus.QUARANTINED

            after_q3_count = await repo.count_available("photosynthesis", DifficultyLevel.EASY)
            assert after_q3_count == 0

            await uow.session.rollback()
    finally:
        await engine.dispose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_question_bank_query_count_no_n_plus_one() -> None:
    """Verify find_questions executes in a single SQL statement with joined topic."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("PostgreSQL database is not accessible")

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with session_factory() as session:
            repo = SQLAlchemyQuestionBank(session)
            topic = await repo.get_or_create_topic("kinematics", "Kinematics")

            questions = [
                Question(
                    topic_id=topic.id,
                    difficulty=DifficultyLevel.MEDIUM,
                    stem=f"Kinematics question {i}",
                    options={"A": "1", "B": "2", "C": "3", "D": "4"},
                    correct_key="A",
                    explanation="Physics rule",
                    content_hash=f"kin_{uuid.uuid4().hex[:12]}",
                    prompt_version="v1",
                    model="gemini-2.5-flash",
                )
                for i in range(5)
            ]
            await repo.insert_questions(questions)
            await session.commit()

        # Count queries executed during find_questions
        query_count = 0

        def count_query(
            conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool
        ) -> None:
            nonlocal query_count
            query_count += 1

        event.listen(engine.sync_engine, "before_cursor_execute", count_query)
        try:
            async with session_factory() as session:
                repo = SQLAlchemyQuestionBank(session)
                results = await repo.find_questions(
                    topic_key="kinematics",
                    difficulty=DifficultyLevel.MEDIUM,
                    limit=5,
                )
                assert len(results) == 5
                # Exactly 1 query executed (single join, no lazy loading N+1 queries)
                assert query_count == 1
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", count_query)

    finally:
        await engine.dispose()
