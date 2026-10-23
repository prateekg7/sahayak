"""Unit tests for CareerPracticeService and practice repository adapter (T8.3)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.config import get_settings
from sahayak.core.db.session import UnitOfWork
from sahayak.core.errors import InvalidInputError, NotFoundError
from sahayak.modules.career.service.practice import CareerPracticeService
from sahayak.shared.users.models import User


@pytest.mark.asyncio
async def test_career_practice_service_workflow() -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    user_id = uuid.uuid4()
    service = CareerPracticeService(session_factory=session_factory)

    try:
        async with UnitOfWork(session_factory) as uow:
            uow.session.add(User(id=user_id))
            await uow.session.commit()

        # 1. Improve bullet
        bullet = "Managed deployment of real-time messaging pipeline"
        imp_data, imp_spoken, imp_actions = await service.improve_bullet(bullet)
        assert imp_data["action"] == "Managed"
        assert len(imp_data["improved_variations"]) >= 2
        assert len(imp_spoken) <= 300
        assert "*" not in imp_spoken
        assert len(imp_actions) == 2

        # 2. Daily question for new user (unanswered)
        q_data, q_spoken, q_actions = await service.get_daily_question(user_id=user_id)
        assert "question_key" in q_data
        assert "topic" in q_data
        assert "question_text" in q_data
        assert len(q_spoken) <= 300
        assert "*" not in q_spoken
        q_key = q_data["question_key"]

        # 3. Check answer to daily question
        ans_data, ans_spoken, ans_actions = await service.check_daily_answer(
            user_id=user_id,
            question_key=q_key,
            answer="STAR stands for situation, task, action, and result.",
        )
        assert ans_data["question_key"] == q_key
        assert ans_data["is_correct"] is True
        assert ans_data["stats"]["total_attempts"] == 1
        assert len(ans_spoken) <= 300
        assert "*" not in ans_spoken

        # 4. Next daily question rotates to a different question
        next_q_data, _, _ = await service.get_daily_question(user_id=user_id)
        assert next_q_data["question_key"] != q_key

        # 5. Answering non-existent question raises NotFoundError
        with pytest.raises(NotFoundError):
            await service.check_daily_answer(
                user_id=user_id,
                question_key="non_existent_key_999",
                answer="Sample answer",
            )

        # 6. Improving empty bullet raises InvalidInputError
        with pytest.raises(InvalidInputError):
            await service.improve_bullet("   ")
    finally:
        await engine.dispose()
