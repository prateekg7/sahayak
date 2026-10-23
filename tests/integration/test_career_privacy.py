"""Integration test for career module privacy export and erasure hooks (T8.1)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.config import get_settings
from sahayak.core.db.session import UnitOfWork
from sahayak.core.module import Deps
from sahayak.modules.career.module import module as career_module
from sahayak.modules.career.service.applications import ApplicationService
from sahayak.modules.career.service.interview import InterviewService
from sahayak.modules.career.service.practice import CareerPracticeService
from sahayak.shared.users.models import User


@pytest.mark.asyncio
async def test_career_privacy_export_and_delete() -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    user_id = uuid.uuid4()
    async with UnitOfWork(session_factory) as uow:
        uow.session.add(User(id=user_id))
        await uow.session.commit()

    deps = Deps(session_factory=session_factory)
    career_module.register_tools(None, deps=deps)

    service = InterviewService(session_factory=session_factory)
    app_service = ApplicationService(session_factory=session_factory)
    practice_service = CareerPracticeService(session_factory=session_factory)

    try:
        # Start a session
        start_data, _, _ = await service.start_session(
            user_id=user_id,
            role="Software Engineer",
            level="mid",
            total_questions=2,
        )
        session_id = start_data["session_id"]

        # Answer question
        await service.answer_question(
            user_id=user_id,
            session_id_str=session_id,
            answer="I built scalable microservices with gRPC and Python.",
        )

        # Add job application
        await app_service.add_application(
            user_id=user_id,
            company="OpenAI",
            role="Research Engineer",
            status="applied",
        )

        # Record daily practice answer
        await practice_service.check_daily_answer(
            user_id=user_id,
            question_key="star_method_intro",
            answer="Situation task action result",
        )

        # 1. Export user data
        exported = await career_module.export_user_data(str(user_id))
        assert "interview_sessions" in exported
        sessions = exported["interview_sessions"]
        assert len(sessions) == 1
        assert sessions[0]["id"] == session_id
        assert len(sessions[0]["turns"]) == 1
        assert "microservices" in sessions[0]["turns"][0]["user_answer"]

        assert "applications" in exported
        apps = exported["applications"]
        assert len(apps) == 1
        assert apps[0]["company"] == "OpenAI"

        assert "daily_practice" in exported
        practices = exported["daily_practice"]
        assert len(practices) == 1
        assert practices[0]["question_key"] == "star_method_intro"

        # 2. Delete user data (GDPR Right to Erasure)
        await career_module.delete_user_data(str(user_id))

        # 3. Export again should be completely empty
        post_delete = await career_module.export_user_data(str(user_id))
        assert len(post_delete.get("interview_sessions", [])) == 0
        assert len(post_delete.get("applications", [])) == 0
        assert len(post_delete.get("daily_practice", [])) == 0
    finally:
        await engine.dispose()
