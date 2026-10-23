"""Unit and property tests for progress, streak, and weak topics domain logic (T3.13)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from hypothesis import given
from hypothesis import strategies as st

from sahayak.modules.academics.domain.progress import (
    StreakInfo,
    TopicStatSummary,
    calculate_streak,
    calculate_weak_topics,
    calculate_weekly_summary,
    format_streak_spoken,
    format_summary_spoken,
    format_weak_topics_spoken,
    format_weekly_spoken,
    timestamps_to_dates,
)


def test_calculate_streak_empty() -> None:
    """Empty activity history yields zero streak."""
    today = date(2026, 10, 23)
    info = calculate_streak([], today=today)
    assert info == StreakInfo(
        current_streak=0,
        longest_streak=0,
        studied_today=False,
        last_active_date=None,
    )


def test_calculate_streak_today_only() -> None:
    """Studying today starts a 1-day streak."""
    today = date(2026, 10, 23)
    info = calculate_streak([today], today=today)
    assert info.current_streak == 1
    assert info.longest_streak == 1
    assert info.studied_today is True
    assert info.last_active_date == today


def test_calculate_streak_yesterday_only() -> None:
    """Studying yesterday preserves the streak until end of today."""
    today = date(2026, 10, 23)
    yesterday = date(2026, 10, 22)
    info = calculate_streak([yesterday], today=today)
    assert info.current_streak == 1
    assert info.longest_streak == 1
    assert info.studied_today is False
    assert info.last_active_date == yesterday


def test_calculate_streak_consecutive_days_ending_today() -> None:
    """Consecutive days ending today yields exact length."""
    today = date(2026, 10, 23)
    dates = [today - timedelta(days=i) for i in range(5)]  # 5 days: today through 4 days ago
    info = calculate_streak(dates, today=today)
    assert info.current_streak == 5
    assert info.longest_streak == 5
    assert info.studied_today is True


def test_calculate_streak_consecutive_days_ending_yesterday() -> None:
    """Consecutive days ending yesterday preserves the full count."""
    today = date(2026, 10, 23)
    dates = [today - timedelta(days=i) for i in range(1, 4)]  # 3 days: yesterday, 2 ago, 3 ago
    info = calculate_streak(dates, today=today)
    assert info.current_streak == 3
    assert info.longest_streak == 3
    assert info.studied_today is False


def test_calculate_streak_broken() -> None:
    """Gap of more than 1 day resets current streak to zero."""
    today = date(2026, 10, 23)
    dates = [today - timedelta(days=3), today - timedelta(days=4)]
    info = calculate_streak(dates, today=today)
    assert info.current_streak == 0
    assert info.longest_streak == 2
    assert info.studied_today is False


def test_calculate_streak_multiple_runs() -> None:
    """Longest streak tracks historical best across interruptions."""
    today = date(2026, 10, 23)
    # Historical run of 5 days: 20 days ago to 16 days ago
    hist_run = [today - timedelta(days=d) for d in range(16, 21)]
    # Current run of 2 days: yesterday and today
    current_run = [today - timedelta(days=1), today]
    info = calculate_streak(hist_run + current_run, today=today)
    assert info.current_streak == 2
    assert info.longest_streak == 5
    assert info.studied_today is True


def test_calculate_streak_duplicate_same_day_activities() -> None:
    """Multiple activities on the same date count as 1 day."""
    today = date(2026, 10, 23)
    dates = [today, today, today, today - timedelta(days=1), today - timedelta(days=1)]
    info = calculate_streak(dates, today=today)
    assert info.current_streak == 2
    assert info.longest_streak == 2


def test_timestamps_to_dates_timezone_conversion() -> None:
    """Timestamp at 23:30 UTC on Oct 22 is Oct 23 in Asia/Kolkata (+05:30)."""
    ts = datetime(2026, 10, 22, 23, 30, tzinfo=ZoneInfo("UTC"))
    dates = timestamps_to_dates([ts], user_timezone="Asia/Kolkata")
    assert dates == {date(2026, 10, 23)}

    # Same timestamp in UTC is Oct 22
    dates_utc = timestamps_to_dates([ts], user_timezone="UTC")
    assert dates_utc == {date(2026, 10, 22)}


def test_timestamps_to_dates_invalid_tz_fallback() -> None:
    """Invalid timezone falls back to UTC without error."""
    ts = datetime(2026, 10, 23, 10, 0, tzinfo=ZoneInfo("UTC"))
    dates = timestamps_to_dates([ts], user_timezone="Invalid/Unknown_Zone")
    assert dates == {date(2026, 10, 23)}


def test_calculate_weak_topics() -> None:
    """Weak topics are ordered ascending by accuracy with eligible threshold."""
    stats = [
        TopicStatSummary(topic="Physics", attempts=10, correct=9, accuracy_pct=90.0),
        TopicStatSummary(topic="Chemistry", attempts=10, correct=4, accuracy_pct=40.0),
        TopicStatSummary(topic="Biology", attempts=10, correct=6, accuracy_pct=60.0),
        TopicStatSummary(topic="Math", attempts=0, correct=0, accuracy_pct=0.0),  # 0 attempts
    ]
    weak = calculate_weak_topics(stats, min_attempts=1, threshold_pct=75.0)
    assert len(weak) == 2
    assert weak[0].topic == "Chemistry"
    assert weak[0].accuracy_pct == 40.0
    assert weak[1].topic == "Biology"
    assert weak[1].accuracy_pct == 60.0


def test_calculate_weekly_summary() -> None:
    """Weekly summary calculates active days within 7-day window."""
    today = date(2026, 10, 23)
    activity_dates = [
        today,
        today - timedelta(days=2),
        today - timedelta(days=5),
        today - timedelta(days=10),  # Outside 7-day window
    ]
    summary = calculate_weekly_summary(
        activity_dates=activity_dates,
        today=today,
        quizzes_completed=3,
        questions_answered=15,
        correct_count=12,
        cards_reviewed=8,
    )
    assert summary.active_days == 3
    assert summary.quizzes_completed == 3
    assert summary.questions_answered == 15
    assert summary.correct_count == 12
    assert summary.accuracy_pct == 80.0
    assert summary.cards_reviewed == 8


@pytest.mark.parametrize(
    "formatter,args",
    [
        (format_summary_spoken, (5, 25, 80.0, 4, "Photosynthesis")),
        (format_summary_spoken, (0, 0, 0.0, 0, None)),
        (format_weak_topics_spoken, ([TopicStatSummary("Chem", 5, 2, 40.0)],)),
        (format_weak_topics_spoken, ([],)),
        (
            format_streak_spoken,
            (
                StreakInfo(
                    current_streak=3,
                    longest_streak=7,
                    studied_today=True,
                    last_active_date=date(2026, 10, 23),
                ),
            ),
        ),
        (
            format_streak_spoken,
            (
                StreakInfo(
                    current_streak=0,
                    longest_streak=0,
                    studied_today=False,
                    last_active_date=None,
                ),
            ),
        ),
        (
            format_weekly_spoken,
            (calculate_weekly_summary([date(2026, 10, 23)], date(2026, 10, 23), 2, 10, 8, 5),),
        ),
    ],
)
def test_spoken_summary_voice_rules(formatter: Any, args: tuple[Any, ...]) -> None:
    """Spoken summaries must be <= 300 characters with no forbidden symbols."""
    text: str = formatter(*args)
    assert len(text) <= 300
    assert "#" not in text
    assert "*" not in text
    assert "[" not in text
    assert "http" not in text


# ---------------------------------------------------------------------------
# Hypothesis Property Tests
# ---------------------------------------------------------------------------


@given(
    days_back=st.lists(st.integers(min_value=0, max_value=100), max_size=50),
)
def test_property_streak_invariants(days_back: list[int]) -> None:
    """Hypothesis property test verifying streak invariants across arbitrary histories."""
    today = date(2026, 10, 23)
    dates = [today - timedelta(days=d) for d in days_back]

    info = calculate_streak(dates, today=today)

    # 1. Longest streak is always >= current streak
    assert info.longest_streak >= info.current_streak

    # 2. If 0 is in days_back, studied_today must be True
    if 0 in days_back:
        assert info.studied_today is True
        assert info.current_streak >= 1
    else:
        assert info.studied_today is False

    # 3. If neither 0 nor 1 is in days_back, current streak must be 0
    if 0 not in days_back and 1 not in days_back:
        assert info.current_streak == 0
