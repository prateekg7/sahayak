"""Unit and property-based tests for deterministic study plan scheduling (T3.11)."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from hypothesis import given, settings
from hypothesis import strategies as st

from sahayak.modules.academics.domain.planner import (
    PlanSchedule,
    TopicWeight,
    generate_study_plan,
    resolve_current_date,
)


def test_planner_exam_date_in_past_or_today() -> None:
    """Exam date on or before start date returns an infeasible plan schedule."""
    today = date(2026, 10, 23)
    topics = ["Algebra", "Geometry"]

    # Exam today
    plan_today = generate_study_plan(
        exam_date=today,
        topics=topics,
        start_date=today,
    )
    assert plan_today.is_feasible is False
    assert plan_today.total_days == 0
    assert plan_today.tasks == []
    assert "after today" in (plan_today.warning or "").lower()

    # Exam in the past
    plan_past = generate_study_plan(
        exam_date=today - timedelta(days=2),
        topics=topics,
        start_date=today,
    )
    assert plan_past.is_feasible is False
    assert plan_past.total_days == 0


def test_planner_empty_topics() -> None:
    """Empty or whitespace-only topics returns an infeasible plan schedule."""
    today = date(2026, 10, 23)
    plan = generate_study_plan(
        exam_date=today + timedelta(days=5),
        topics=["   ", ""],
        start_date=today,
    )
    assert plan.is_feasible is False
    assert plan.tasks == []
    assert "at least one topic" in (plan.warning or "").lower()


def test_planner_standard_14_day_schedule() -> None:
    """14-day study plan schedules learning across 12 days and review on the final 2 days."""
    today = date(2026, 10, 23)
    exam = today + timedelta(days=14)
    topics = [
        TopicWeight(name="Thermodynamics", weight=2.0),
        TopicWeight(name="Fluid Mechanics", weight=1.0),
        TopicWeight(name="Heat Transfer", weight=1.5),
    ]

    schedule = generate_study_plan(
        exam_date=exam,
        topics=topics,
        hours_per_day=2.0,
        start_date=today,
    )

    assert schedule.is_feasible is True
    assert schedule.total_days == 14
    assert schedule.daily_minutes_capacity == 120
    assert schedule.total_minutes > 0
    assert schedule.uncovered_topics == []

    # Verify per-day capacity invariant
    day_minutes: dict[date, int] = defaultdict(int)
    for task in schedule.tasks:
        day_minutes[task.date] += task.minutes
        assert task.minutes > 0

    for day, minutes in day_minutes.items():
        assert minutes <= schedule.daily_minutes_capacity, (
            f"Day {day} exceeded capacity: {minutes} > {schedule.daily_minutes_capacity}"
        )

    # Verify final 2 days are dedicated review days
    final_day_1 = exam - timedelta(days=2)
    final_day_2 = exam - timedelta(days=1)

    final_1_tasks = [t for t in schedule.tasks if t.date == final_day_1]
    final_2_tasks = [t for t in schedule.tasks if t.date == final_day_2]

    assert any("review" in t.topic.lower() for t in final_1_tasks)
    assert any("review" in t.topic.lower() for t in final_2_tasks)

    # Verify all topics were scheduled
    scheduled_topics = {t.topic for t in schedule.tasks}
    assert "Thermodynamics" in scheduled_topics
    assert "Fluid Mechanics" in scheduled_topics
    assert "Heat Transfer" in scheduled_topics


def test_planner_tight_schedule_generates_warning() -> None:
    """Too many topics for a short duration produces an infeasible plan with uncovered topics."""
    today = date(2026, 10, 23)
    exam = today + timedelta(days=2)  # Only 2 days available
    topics = [f"Chapter {i}" for i in range(1, 15)]  # 14 chapters

    schedule = generate_study_plan(
        exam_date=exam,
        topics=topics,
        hours_per_day=1.0,  # 60 min daily
        start_date=today,
    )

    assert schedule.is_feasible is False
    assert len(schedule.uncovered_topics) > 0
    assert schedule.warning is not None


def test_planner_timezone_resolution() -> None:
    """resolve_current_date respects localized timezone boundaries."""
    # 2026-10-23 20:00 UTC -> 2026-10-24 01:30 in Asia/Kolkata (+05:30)
    clock_dt = datetime(2026, 10, 23, 20, 0, 0, tzinfo=UTC)

    utc_date = resolve_current_date(clock=lambda: clock_dt, user_timezone="UTC")
    assert utc_date == date(2026, 10, 23)

    ist_date = resolve_current_date(clock=lambda: clock_dt, user_timezone="Asia/Kolkata")
    assert ist_date == date(2026, 10, 24)

    # Invalid timezone falls back safely to UTC
    fallback_date = resolve_current_date(
        clock=lambda: clock_dt, user_timezone="NonExistent/Timezone"
    )
    assert fallback_date == date(2026, 10, 23)


@given(
    days_to_exam=st.integers(min_value=1, max_value=60),
    hours_per_day=st.floats(min_value=0.5, max_value=8.0),
    num_topics=st.integers(min_value=1, max_value=8),
)
@settings(max_examples=50)
def test_planner_property_invariants(
    days_to_exam: int,
    hours_per_day: float,
    num_topics: int,
) -> None:
    """Hypothesis properties: daily capacity is never exceeded, review is at the end,
    and coverage is complete or reported.
    """
    start = date(2026, 10, 23)
    exam = start + timedelta(days=days_to_exam)
    topics = [f"Topic-{i}" for i in range(num_topics)]

    schedule: PlanSchedule = generate_study_plan(
        exam_date=exam,
        topics=topics,
        hours_per_day=hours_per_day,
        start_date=start,
    )

    assert schedule.total_days == days_to_exam
    daily_cap = schedule.daily_minutes_capacity

    # Property 1: Daily minutes never exceed daily_capacity for ANY day
    day_minutes: dict[date, int] = defaultdict(int)
    for task in schedule.tasks:
        day_minutes[task.date] += task.minutes
        assert start <= task.date < exam, f"Task date {task.date} out of range [{start}, {exam})"

    for day, minutes in day_minutes.items():
        assert minutes <= daily_cap, f"Day {day} exceeded capacity: {minutes} > {daily_cap}"

    # Property 2: Last day(s) before exam are dedicated review days
    last_study_day = exam - timedelta(days=1)
    last_day_tasks = [t for t in schedule.tasks if t.date == last_study_day]
    assert len(last_day_tasks) > 0, "Last study day should have scheduled tasks"
    assert any("review" in t.topic.lower() for t in last_day_tasks), (
        f"Last day {last_study_day} tasks {last_day_tasks} missing review task"
    )

    # Property 3: Every topic is either covered in tasks or reported in uncovered_topics
    covered = {t.topic for t in schedule.tasks}
    uncovered = set(schedule.uncovered_topics)
    for topic in topics:
        assert (topic in covered) or (topic in uncovered), (
            f"Topic {topic} was neither covered nor reported as uncovered"
        )

    # If there are uncovered topics, plan must be marked infeasible
    if uncovered:
        assert schedule.is_feasible is False
        assert schedule.warning is not None
