"""Unit tests for InterviewService and evaluator (T8.1)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.config import get_settings
from sahayak.core.db.session import UnitOfWork
from sahayak.core.errors import InvalidInputError, NotFoundError
from sahayak.modules.career.service.interview import InterviewService
from sahayak.shared.llm.fake import FakeLLMClient
from sahayak.shared.users.models import User


@pytest.mark.asyncio
async def test_interview_service_full_lifecycle_with_fake_llm() -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    user_id = uuid.uuid4()
    async with UnitOfWork(session_factory) as uow:
        uow.session.add(User(id=user_id))
        await uow.session.commit()

    # Configure FakeLLMClient with canned JSON responses
    canned_eval_1 = {
        "clarity_score": 4,
        "relevance_score": 4,
        "depth_score": 3,
        "feedback_tips": ["Mention specific tech stack details."],
        "feedback_spoken": "Solid answer with clear explanation.",
    }
    canned_eval_2 = {
        "clarity_score": 5,
        "relevance_score": 5,
        "depth_score": 4,
        "feedback_tips": ["Quantify user impact."],
        "feedback_spoken": "Outstanding answer covering all core points.",
    }
    fake_llm = FakeLLMClient(canned_json=[canned_eval_1, canned_eval_2])

    service = InterviewService(
        session_factory=session_factory,
        llm_client=fake_llm,
    )

    try:
        # 1. Start a 2-question interview
        start_data, start_spoken, start_next = await service.start_session(
            user_id=user_id,
            role="Software Engineer",
            level="mid",
            total_questions=2,
        )
        assert start_data["status"] == "in_progress"
        assert start_data["total_questions"] == 2
        assert "Software Engineer" in start_spoken
        session_id = start_data["session_id"]

        # 2. Answer question 1
        ans1_data, ans1_spoken, ans1_next = await service.answer_question(
            user_id=user_id,
            session_id_str=session_id,
            answer="I optimized database queries by adding indexes and caching with Redis.",
        )
        assert ans1_data["status"] == "in_progress"
        assert ans1_data["score"]["clarity_score"] == 4
        assert ans1_data["next_question_index"] == 1
        assert "Solid answer" in ans1_spoken

        # 3. Answer question 2 (final question -> completes session)
        ans2_data, ans2_spoken, ans2_next = await service.answer_question(
            user_id=user_id,
            session_id_str=session_id,
            answer="I handled the outage by rolling back the canary deployment.",
        )
        assert ans2_data["status"] == "completed"
        assert ans2_data["overall_summary"]["total_questions"] == 2
        assert ans2_data["overall_summary"]["overall_average_score"] > 0
        assert "Interview complete" in ans2_spoken or "completed all 2 questions" in ans2_spoken

        # 4. Answering again on completed session raises InvalidInputError
        with pytest.raises(InvalidInputError):
            await service.answer_question(
                user_id=user_id,
                session_id_str=session_id,
                answer="Another answer",
            )

        # 5. History shows completed session
        hist_data, hist_spoken, _ = await service.get_history(user_id=user_id)
        assert len(hist_data["sessions"]) >= 1
        assert hist_data["sessions"][0]["session_id"] == session_id
        assert hist_data["sessions"][0]["status"] == "completed"
        assert hist_data["sessions"][0]["questions_completed"] == 2
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_interview_service_early_finish_and_isolation() -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    async with UnitOfWork(session_factory) as uow:
        uow.session.add(User(id=user_a))
        uow.session.add(User(id=user_b))
        await uow.session.commit()

    service = InterviewService(session_factory=session_factory)

    try:
        # User A starts interview
        start_data, _, _ = await service.start_session(
            user_id=user_a,
            role="Product Manager",
            level="senior",
            total_questions=3,
        )
        session_id = start_data["session_id"]

        # User B attempts to finish User A's session -> raises NotFoundError
        with pytest.raises(NotFoundError):
            await service.finish_session(
                user_id=user_b,
                session_id_str=session_id,
            )

        # User A finishes early
        fin_data, fin_spoken, _ = await service.finish_session(
            user_id=user_a,
            session_id_str=session_id,
        )
        assert fin_data["status"] == "abandoned"
        assert fin_data["answered_questions"] == 0
        assert "finished" in fin_spoken.lower()
    finally:
        await engine.dispose()
