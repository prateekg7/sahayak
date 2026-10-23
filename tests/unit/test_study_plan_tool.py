"""Unit tests for study_plan tool, date parser, and StudyPlanService (T3.12)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.auth.principal import Principal, set_current_principal
from sahayak.core.config import get_settings
from sahayak.core.db.session import UnitOfWork
from sahayak.modules.academics.domain.planner import parse_exam_date
from sahayak.modules.academics.service.plan import (
    StudyPlanService,
)
from sahayak.modules.academics.tools.study_plan import (
    study_plan,
)
from sahayak.shared.llm.fake import FakeLLMClient
from sahayak.shared.users.models import User


def test_parse_exam_date_variants() -> None:
    """Test date parsing with ISO, relative, and natural spoken date phrases."""
    base = date(2026, 10, 23)

    # 1. ISO format
    assert parse_exam_date("2026-11-15", base) == date(2026, 11, 15)
    assert parse_exam_date("2026-12-01T10:00:00Z", base) == date(2026, 12, 1)

    # 2. Relative keywords
    assert parse_exam_date("tomorrow", base) == date(2026, 10, 24)
    assert parse_exam_date("next week", base) == date(2026, 10, 30)
    assert parse_exam_date("in 1 week", base) == date(2026, 10, 30)
    assert parse_exam_date("in 2 weeks", base) == date(2026, 11, 6)
    assert parse_exam_date("in 5 days", base) == date(2026, 10, 28)
    assert parse_exam_date("in 1 month", base) == date(2026, 11, 22)

    # 3. Spoken day of month
    # 28th > 23rd -> current month (Oct 28)
    assert parse_exam_date("on the 28th", base) == date(2026, 10, 28)
    assert parse_exam_date("28th", base) == date(2026, 10, 28)
    # 15th < 23rd -> rolls over to next month (Nov 15)
    assert parse_exam_date("on the 15th", base) == date(2026, 11, 15)
    assert parse_exam_date("the 15th", base) == date(2026, 11, 15)

    # 4. Month names
    assert parse_exam_date("November 15", base) == date(2026, 11, 15)
    assert parse_exam_date("Nov 15th", base) == date(2026, 11, 15)
    assert parse_exam_date("15th of November", base) == date(2026, 11, 15)
    assert parse_exam_date("Nov 15, 2026", base) == date(2026, 11, 15)


def test_parse_exam_date_invalid_and_past() -> None:
    """Test rejection of past dates, empty inputs, and unrecognized strings."""
    base = date(2026, 10, 23)

    # Past date
    with pytest.raises(ValueError, match="future"):
        parse_exam_date("2026-10-20", base)

    # Today is not in the future
    with pytest.raises(ValueError, match="future"):
        parse_exam_date("2026-10-23", base)

    # Empty
    with pytest.raises(ValueError, match="empty"):
        parse_exam_date("   ", base)

    # Unrecognized
    with pytest.raises(ValueError, match="Could not parse"):
        parse_exam_date("some random text", base)


@pytest.mark.asyncio
async def test_study_plan_service_create_and_query() -> None:
    """Test study plan creation with explicit topics and retrieval."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    fixed_now = datetime(2026, 10, 23, 10, 0, tzinfo=UTC)
    service = StudyPlanService(
        session_factory=session_factory,
        clock=lambda: fixed_now,
    )

    user_id = uuid.uuid4()
    async with UnitOfWork(session_factory) as uow:
        uow.session.add(User(id=user_id))
        await uow.session.flush()

    exam_date_str = "2026-11-05"
    topics = ["Derivatives", "Integrals", "Limits"]

    data, spoken = await service.create_study_plan(
        user_id=user_id,
        goal="Calculus Final Exam",
        exam_date_str=exam_date_str,
        topics=topics,
        hours_per_day=1.5,
    )

    assert data.action == "create"
    assert data.plan_id is not None
    assert data.total_days == 13
    assert data.tasks is not None
    assert len(data.tasks) > 0
    assert "Calculus Final Exam" in spoken
    assert "tasks" in spoken

    # Retrieve today's tasks
    plan_uuid = uuid.UUID(data.plan_id)
    today_data, today_spoken = await service.get_today_tasks(user_id=user_id, plan_id=plan_uuid)
    assert today_data.action == "today"
    assert today_data.today_tasks is not None
    assert len(today_data.today_tasks) > 0
    assert "tasks scheduled for today" in today_spoken or "study task" in today_spoken

    # List plans
    list_data, list_spoken = await service.list_plans(user_id=user_id)
    assert list_data.action == "list"
    assert list_data.plans is not None
    assert len(list_data.plans) >= 1
    assert any(p.plan_id == data.plan_id for p in list_data.plans)


@pytest.mark.asyncio
async def test_study_plan_service_llm_topic_breakdown() -> None:
    """Test topic breakdown generation via FakeLLMClient when topics are not provided."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    fake_llm = FakeLLMClient(
        canned_json={
            "topics": [
                "Organic Nomenclature",
                "Reaction Mechanisms",
                "Stereochemistry",
            ]
        }
    )

    fixed_now = datetime(2026, 10, 23, 10, 0, tzinfo=UTC)
    service = StudyPlanService(
        session_factory=session_factory,
        llm_client=fake_llm,
        clock=lambda: fixed_now,
    )

    user_id = uuid.uuid4()
    async with UnitOfWork(session_factory) as uow:
        uow.session.add(User(id=user_id))
        await uow.session.flush()

    data, spoken = await service.create_study_plan(
        user_id=user_id,
        goal="Organic Chemistry",
        exam_date_str="2026-11-10",
        topics=None,  # triggers LLM breakdown
        hours_per_day=2.0,
    )

    assert data.action == "create"
    assert data.tasks is not None
    task_topics = {t.topic for t in data.tasks}
    assert any("Organic Nomenclature" in t for t in task_topics)


@pytest.mark.asyncio
async def test_study_plan_service_update_task_and_replan() -> None:
    """Test marking a study plan task as done and replanning remaining days."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    fixed_now = datetime(2026, 10, 23, 10, 0, tzinfo=UTC)
    service = StudyPlanService(
        session_factory=session_factory,
        clock=lambda: fixed_now,
    )

    user_id = uuid.uuid4()
    async with UnitOfWork(session_factory) as uow:
        uow.session.add(User(id=user_id))
        await uow.session.flush()

    data, _ = await service.create_study_plan(
        user_id=user_id,
        goal="Physics Mechanics",
        exam_date_str="2026-11-12",
        topics=["Kinematics", "Dynamics", "Energy"],
        hours_per_day=1.0,
    )

    assert data.tasks is not None
    first_task = data.tasks[0]

    # 1. Mark task as done
    update_data, update_spoken = await service.update_plan(
        user_id=user_id,
        task_id=uuid.UUID(first_task.task_id),
        mark_done=True,
    )
    assert update_data.updated_task is not None
    assert update_data.updated_task.done is True
    assert "completed" in update_spoken

    # 2. Replan remaining days
    replan_data, replan_spoken = await service.update_plan(
        user_id=user_id,
        plan_id=uuid.UUID(data.plan_id or ""),
        replan=True,
        hours_per_day=2.0,
    )
    assert replan_data.tasks is not None
    assert "replanned" in replan_spoken


@pytest.mark.asyncio
async def test_study_plan_tool_anonymous_rejected() -> None:
    """Anonymous callers must receive auth_required error envelope."""
    set_current_principal(Principal(user_id=None, anonymous=True))

    res = await study_plan(
        action="create",
        goal="Chemistry",
        exam_date="2026-11-20",
    )
    assert res.get("ok") is False
    assert res.get("error_code") == "auth_required"


@pytest.mark.asyncio
async def test_study_plan_tool_input_validation() -> None:
    """Input validation errors map to invalid_input error code."""
    user_id = uuid.uuid4()
    principal = Principal(
        user_id=user_id,
        scopes=frozenset({"academics.write"}),
        anonymous=False,
    )
    set_current_principal(principal)

    # Missing goal
    res_no_goal = await study_plan(action="create", exam_date="2026-11-20")
    assert res_no_goal.get("ok") is False
    assert res_no_goal.get("error_code") == "invalid_input"

    # Missing exam date
    res_no_date = await study_plan(action="create", goal="Chemistry")
    assert res_no_date.get("ok") is False
    assert res_no_date.get("error_code") == "invalid_input"

    # Past exam date
    res_past = await study_plan(action="create", goal="Chemistry", exam_date="2020-01-01")
    assert res_past.get("ok") is False
    assert res_past.get("error_code") == "invalid_input"
