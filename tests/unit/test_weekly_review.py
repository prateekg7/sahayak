"""Unit tests for cross-module weekly report domain and service (T13.2)."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from sahayak.modules.academics.domain.progress import StreakInfo
from sahayak.modules.productivity.domain.weekly_review import (
    WeeklyFinanceStats,
    WeeklyHabitStats,
    WeeklyHealthStats,
    WeeklyReviewSummary,
    WeeklyStudyStats,
    format_weekly_review_spoken,
)
from sahayak.modules.productivity.service.weekly_review import WeeklyReviewService


def test_format_weekly_review_empty_data() -> None:
    """When no activity exists across any enabled module, a clear actionable prompt is spoken."""
    summary = WeeklyReviewSummary()
    spoken = format_weekly_review_spoken(summary)
    assert "No activity recorded this week yet" in spoken
    assert len(spoken) <= 300
    assert not re.search(r"[*_#`\[\]]", spoken)


def test_format_weekly_review_all_modules_present() -> None:
    """Combines study, habits, finance, and health in concise spoken ordering with highlight."""
    summary = WeeklyReviewSummary(
        enabled_modules=["academics", "productivity", "finance", "health"],
        study=WeeklyStudyStats(
            quizzes_completed=5,
            questions_answered=25,
            accuracy_pct=84.0,
            streak_days=7,
            is_streak_record=True,
        ),
        habits=WeeklyHabitStats(
            active_count=3,
            completions_count=6,
            top_habit="Reading",
        ),
        finance=WeeklyFinanceStats(
            total_spent_minor=145000,
            currency="INR",
        ),
        health=WeeklyHealthStats(
            workouts_count=4,
            avg_daily_water_ml=2200,
            active_days=5,
        ),
        highlights=["Longest study streak ever at 7 days"],
    )

    spoken = format_weekly_review_spoken(summary)
    assert "5 quizzes with 84% accuracy" in spoken
    assert "logged 6 habit sessions" in spoken
    assert "spent 1,450 INR" in spoken
    assert "logged 4 workouts" in spoken
    assert "Highlight: Longest study streak ever at 7 days!" in spoken
    assert len(spoken) <= 300
    assert not re.search(r"[*_#`\[\]]", spoken)


@pytest.mark.parametrize(
    ("study", "habits", "finance", "health", "expected_phrase"),
    [
        (
            WeeklyStudyStats(quizzes_completed=3, accuracy_pct=90.0),
            None,
            None,
            None,
            "completed 3 quizzes with 90% accuracy",
        ),
        (
            None,
            WeeklyHabitStats(completions_count=4),
            None,
            None,
            "logged 4 habit sessions",
        ),
        (
            None,
            None,
            WeeklyFinanceStats(total_spent_minor=50000, currency="INR"),
            None,
            "spent 500 INR",
        ),
        (
            None,
            None,
            None,
            WeeklyHealthStats(workouts_count=2),
            "logged 2 workouts",
        ),
    ],
)
def test_format_weekly_review_single_module_subsets(
    study: WeeklyStudyStats | None,
    habits: WeeklyHabitStats | None,
    finance: WeeklyFinanceStats | None,
    health: WeeklyHealthStats | None,
    expected_phrase: str,
) -> None:
    """Spoken output adapts cleanly to individual modules without awkward grammar."""
    summary = WeeklyReviewSummary(
        study=study,
        habits=habits,
        finance=finance,
        health=health,
    )
    spoken = format_weekly_review_spoken(summary)
    assert expected_phrase in spoken
    assert len(spoken) <= 300
    assert not re.search(r"[*_#`\[\]]", spoken)


@pytest.mark.asyncio
async def test_weekly_review_service_adaptive_module_queries() -> None:
    """Service queries only available module APIs and aggregates results gracefully."""
    fake_user_id = uuid.uuid4()
    fixed_now = datetime(2026, 10, 24, 12, 0, 0, tzinfo=UTC)

    # Mock Academics API
    academics_mock = AsyncMock()
    academics_mock.get_weekly_summary.return_value = {
        "quizzes_completed": 4,
        "questions_answered": 20,
        "accuracy_pct": 75.0,
    }
    academics_mock.get_streak_info.return_value = StreakInfo(
        current_streak=5,
        longest_streak=5,
        studied_today=True,
        last_active_date=None,
    )

    # Mock Habits API
    prod_mock = AsyncMock()
    prod_mock.get_weekly_habit_stats.return_value = {
        "active_count": 2,
        "completions_count": 5,
        "top_habit": "Yoga",
    }

    # Mock Finance API failing with error to test resilience
    finance_mock = AsyncMock()
    finance_mock.get_total_spending.side_effect = RuntimeError("DB timeout")

    # Health API is not enabled (None)
    def module_api_getter(name: str) -> object | None:
        if name == "academics":
            return academics_mock
        if name == "productivity":
            return prod_mock
        if name == "finance":
            return finance_mock
        return None

    service = WeeklyReviewService(
        session_factory=None,
        module_api_getter=module_api_getter,
        clock=lambda: fixed_now,
    )

    spoken, summary, next_actions = await service.get_weekly_review(
        user_id=fake_user_id, timezone_str="UTC"
    )

    assert "academics" in summary.enabled_modules
    assert "productivity" in summary.enabled_modules
    assert "finance" in summary.enabled_modules
    assert "health" not in summary.enabled_modules

    assert summary.study is not None
    assert summary.study.quizzes_completed == 4
    assert summary.habits is not None
    assert summary.habits.completions_count == 5
    assert summary.finance is None  # Error was caught gracefully

    assert "4 quizzes with 75% accuracy" in spoken
    assert "logged 5 habit sessions" in spoken
    assert len(spoken) <= 300
    assert len(next_actions) > 0
