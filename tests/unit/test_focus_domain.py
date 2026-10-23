"""Unit tests for focus timer domain logic and time calculations (T5.4)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from sahayak.core.errors import InvalidInputError
from sahayak.modules.productivity.domain.focus import (
    calculate_session_remaining,
    format_history_spoken,
    format_session_start_spoken,
    format_session_status_spoken,
    format_session_stop_spoken,
    validate_duration_minutes,
)


def test_validate_duration_minutes() -> None:
    assert validate_duration_minutes(None) == 25
    assert validate_duration_minutes(1) == 1
    assert validate_duration_minutes(25) == 25
    assert validate_duration_minutes(180) == 180

    with pytest.raises(InvalidInputError, match="must be between"):
        validate_duration_minutes(0)

    with pytest.raises(InvalidInputError, match="must be between"):
        validate_duration_minutes(181)


def test_calculate_session_remaining_inactive() -> None:
    now = datetime(2026, 10, 23, 10, 0, 0, tzinfo=UTC)
    planned = now + timedelta(minutes=25)
    rem, is_active, should_complete = calculate_session_remaining(planned, now, "completed")
    assert rem == 0
    assert is_active is False
    assert should_complete is False


def test_calculate_session_remaining_active() -> None:
    now = datetime(2026, 10, 23, 10, 0, 0, tzinfo=UTC)
    planned = now + timedelta(minutes=25)

    # 10 minutes in
    current = now + timedelta(minutes=10)
    rem, is_active, should_complete = calculate_session_remaining(planned, current, "active")
    assert rem == 15 * 60
    assert is_active is True
    assert should_complete is False

    # Exactly at end
    current_end = planned
    rem_end, is_active_end, should_complete_end = calculate_session_remaining(
        planned, current_end, "active"
    )
    assert rem_end == 0
    assert is_active_end is False
    assert should_complete_end is True

    # 5 minutes past end
    current_past = planned + timedelta(minutes=5)
    rem_past, is_active_past, should_complete_past = calculate_session_remaining(
        planned, current_past, "active"
    )
    assert rem_past == 0
    assert is_active_past is False
    assert should_complete_past is True


def test_spoken_formats_and_length() -> None:
    start_spoken = format_session_start_spoken(25, "Biochemistry revision")
    assert "Started a 25 minute focus session for Biochemistry revision" in start_spoken
    assert len(start_spoken) <= 300

    active_spoken = format_session_status_spoken(
        15 * 60, 25, "Biochemistry revision", is_completed=False
    )
    assert "15 minutes remaining" in active_spoken
    assert len(active_spoken) <= 300

    less_one_spoken = format_session_status_spoken(
        45, 25, "Biochemistry revision", is_completed=False
    )
    assert "less than 1 minute remaining" in less_one_spoken

    completed_spoken = format_session_status_spoken(
        0, 25, "Biochemistry revision", is_completed=True
    )
    assert "is finished. Great job staying focused." in completed_spoken
    assert len(completed_spoken) <= 300

    stop_spoken = format_session_stop_spoken(18, "Biochemistry revision")
    assert "stopped after 18 minutes." in stop_spoken
    assert len(stop_spoken) <= 300

    history_spoken = format_history_spoken(4, 100, 2)
    assert "completed 4 focus sessions totaling 100 minutes. Today you completed 2 sessions." in (
        history_spoken
    )
    assert len(history_spoken) <= 300
