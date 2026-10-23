"""Integration tests for Academics privacy export and GDPR deletion across all 8 tables (T3.15)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.config import get_settings
from sahayak.core.db.session import UnitOfWork
from sahayak.core.module import Deps, ModuleRegistry
from sahayak.core.privacy import PrivacyCoordinator
from sahayak.modules.academics.adapters.question_bank import SQLAlchemyQuestionBank
from sahayak.modules.academics.models import (
    ActivityLog,
    Card,
    Deck,
    DifficultyLevel,
    PlanTask,
    Question,
    Quiz,
    QuizQuestion,
    QuizStatus,
    StudyPlan,
    TopicStats,
)
from sahayak.modules.academics.module import AcademicsModule
from sahayak.shared.users.models import User
from sahayak.shared.users.service import UserService


@pytest.mark.asyncio
async def test_academics_privacy_export_and_delete_all_tables() -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    user_id = uuid.uuid4()
    now = datetime.now(UTC)

    # 1. Seed user and records in all 8 Academics user tables
    async with UnitOfWork(session_factory) as uow:
        # User
        user = User(id=user_id)
        uow.session.add(user)

        # Topic & Shared Question
        bank = SQLAlchemyQuestionBank(uow.session)
        topic = await bank.get_or_create_topic(
            f"privacy_topic_{uuid.uuid4().hex[:6]}", "Privacy Science"
        )
        q = Question(
            topic_id=topic.id,
            difficulty=DifficultyLevel.MEDIUM,
            stem="What is data privacy?",
            options={
                "A": "Right to control personal data",
                "B": "Public data",
                "C": "Open access",
                "D": "None",
            },
            correct_key="A",
            explanation="Privacy empowers individuals.",
            content_hash=f"priv_{uuid.uuid4().hex[:8]}",
            prompt_version="v1",
            model="test-model",
        )
        uow.session.add(q)
        await uow.session.flush()

        # 1. Deck
        deck = Deck(
            id=uuid.uuid4(),
            user_id=user_id,
            name="Biology Deck",
        )
        uow.session.add(deck)
        await uow.session.flush()

        # 2. Card
        card = Card(
            id=uuid.uuid4(),
            user_id=user_id,
            deck_id=deck.id,
            front="Mitochondria",
            back="Powerhouse of the cell",
            ease=2.5,
            repetitions=1,
            due_at=now + timedelta(days=1),
        )
        uow.session.add(card)

        # 3. Study Plan
        plan = StudyPlan(
            id=uuid.uuid4(),
            user_id=user_id,
            goal="Biology Final",
            exam_date=now.date() + timedelta(days=14),
        )
        uow.session.add(plan)
        await uow.session.flush()

        # 4. Plan Task
        task = PlanTask(
            id=uuid.uuid4(),
            plan_id=plan.id,
            date=now.date(),
            topic="Read Chapter 1",
            minutes=45,
            done_at=None,
        )
        uow.session.add(task)

        # 5. Topic Stats
        stats = TopicStats(
            user_id=user_id,
            topic_id=topic.id,
            attempts=5,
            correct=4,
            last_attempt_at=now,
        )
        uow.session.add(stats)

        # 6. Quiz
        quiz = Quiz(
            id=uuid.uuid4(),
            user_id=user_id,
            topic_id=topic.id,
            difficulty=DifficultyLevel.MEDIUM,
            total=1,
            status=QuizStatus.COMPLETED,
            score_correct=1,
            expires_at=now + timedelta(hours=2),
            finished_at=now,
        )
        uow.session.add(quiz)
        await uow.session.flush()

        # 7. Quiz Question
        qq = QuizQuestion(
            quiz_id=quiz.id,
            position=0,
            question_id=q.id,
            answered_at=now,
            selected_key="A",
            is_correct=True,
        )
        uow.session.add(qq)

        # 8. Activity Log
        activity = ActivityLog(
            id=uuid.uuid4(),
            user_id=user_id,
            activity_type="quiz",
            event_id=uuid.uuid4(),
            created_at=now,
        )
        uow.session.add(activity)

        await uow.session.commit()

    # 2. Setup privacy coordinator
    module = AcademicsModule()
    deps = Deps(session_factory=session_factory)
    module.register_tools(mcp=None, deps=deps)

    registry = ModuleRegistry()
    registry._modules["academics"] = module

    user_service = UserService(session_factory)
    coordinator = PrivacyCoordinator(
        session_factory=session_factory,
        registry=registry,
        user_service=user_service,
    )

    # 3. Export data and verify all 8 tables are present
    bundle = await coordinator.export_user_data(user_id=user_id)
    assert bundle["user_id"] == str(user_id)
    assert "academics" in bundle["modules"]
    academics_data = bundle["modules"]["academics"]

    # Check that each table category has exported user records
    assert len(academics_data["decks"]) == 1
    assert academics_data["decks"][0]["name"] == "Biology Deck"

    assert len(academics_data["cards"]) == 1
    assert academics_data["cards"][0]["front"] == "Mitochondria"

    assert len(academics_data["study_plans"]) == 1
    assert academics_data["study_plans"][0]["goal"] == "Biology Final"

    assert len(academics_data["plan_tasks"]) == 1
    assert academics_data["plan_tasks"][0]["topic"] == "Read Chapter 1"

    assert len(academics_data["topic_stats"]) == 1
    assert academics_data["topic_stats"][0]["attempts"] == 5

    assert len(academics_data["quizzes"]) == 1
    assert academics_data["quizzes"][0]["score_correct"] == 1

    assert len(academics_data["quiz_questions"]) == 1
    assert academics_data["quiz_questions"][0]["selected_key"] == "A"

    assert len(academics_data["activity_log"]) == 1
    assert academics_data["activity_log"][0]["activity_type"] == "quiz"

    # 4. Delete user data (Right to be Forgotten)
    await coordinator.delete_user_data(user_id=user_id)

    # 5. Verify complete erasure across all 8 Academics tables
    async with UnitOfWork(session_factory) as uow:
        # 1. Deck
        d_res = await uow.session.execute(select(Deck).where(Deck.user_id == user_id))
        assert len(d_res.scalars().all()) == 0

        # 2. Card
        c_res = await uow.session.execute(select(Card).where(Card.user_id == user_id))
        assert len(c_res.scalars().all()) == 0

        # 3. Study Plan
        p_res = await uow.session.execute(select(StudyPlan).where(StudyPlan.user_id == user_id))
        assert len(p_res.scalars().all()) == 0

        # 4. Plan Task (checked via plan_id)
        pt_res = await uow.session.execute(select(PlanTask).where(PlanTask.plan_id == plan.id))
        assert len(pt_res.scalars().all()) == 0

        # 5. Topic Stats
        ts_res = await uow.session.execute(select(TopicStats).where(TopicStats.user_id == user_id))
        assert len(ts_res.scalars().all()) == 0

        # 6. Quiz
        q_res = await uow.session.execute(select(Quiz).where(Quiz.user_id == user_id))
        assert len(q_res.scalars().all()) == 0

        # 7. Quiz Question (checked via quiz_id)
        qq_stmt = select(QuizQuestion).where(QuizQuestion.quiz_id == quiz.id)
        qq_res = await uow.session.execute(qq_stmt)
        assert len(qq_res.scalars().all()) == 0

        # 8. Activity Log
        a_stmt = select(ActivityLog).where(ActivityLog.user_id == user_id)
        a_res = await uow.session.execute(a_stmt)
        assert len(a_res.scalars().all()) == 0
