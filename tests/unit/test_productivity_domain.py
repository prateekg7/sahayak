"""Unit tests for productivity domain models and speech formatting (T5.1)."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from sahayak.core.errors import InvalidInputError
from sahayak.modules.productivity.domain.tasks import (
    DAYS_OF_WEEK,
    TaskPriority,
    TaskStatus,
    format_tasks_spoken,
    parse_due_date,
)


def test_parse_due_date_iso_and_keywords() -> None:
    now_utc = datetime(2026, 10, 23, 10, 0, 0, tzinfo=ZoneInfo("UTC"))

    # None or empty
    assert parse_due_date(None, now_utc) is None
    assert parse_due_date("", now_utc) is None
    assert parse_due_date("   ", now_utc) is None

    # Full ISO timestamp
    iso_val = "2026-11-05T14:30:00Z"
    parsed_iso = parse_due_date(iso_val, now_utc)
    assert parsed_iso is not None
    assert parsed_iso == datetime(2026, 11, 5, 14, 30, 0, tzinfo=ZoneInfo("UTC"))

    # Relative keyword: today
    parsed_today = parse_due_date("today", now_utc)
    assert parsed_today is not None
    assert parsed_today == datetime(2026, 10, 23, 18, 0, 0, tzinfo=ZoneInfo("UTC"))

    # Relative keyword: tomorrow
    parsed_tomorrow = parse_due_date("tomorrow", now_utc)
    assert parsed_tomorrow is not None
    assert parsed_tomorrow == datetime(2026, 10, 24, 9, 0, 0, tzinfo=ZoneInfo("UTC"))


def test_parse_due_date_relative_offsets() -> None:
    now_utc = datetime(2026, 10, 23, 10, 0, 0, tzinfo=ZoneInfo("UTC"))

    # "in 3 days"
    parsed_days = parse_due_date("in 3 days", now_utc)
    assert parsed_days is not None
    assert parsed_days.date() == (now_utc + timedelta(days=3)).date()

    # "in 2 weeks"
    parsed_weeks = parse_due_date("in 2 weeks", now_utc)
    assert parsed_weeks is not None
    assert parsed_weeks.date() == (now_utc + timedelta(weeks=2)).date()

    # "in 4 hours"
    parsed_hours = parse_due_date("in 4 hours", now_utc)
    assert parsed_hours is not None
    assert parsed_hours == now_utc + timedelta(hours=4)


def test_parse_due_date_days_of_week() -> None:
    # 2026-10-23 is a Friday (weekday() == 4)
    now_utc = datetime(2026, 10, 23, 10, 0, 0, tzinfo=ZoneInfo("UTC"))

    # "Saturday" (tomorrow)
    parsed_sat = parse_due_date("Saturday", now_utc)
    assert parsed_sat is not None
    assert parsed_sat.weekday() == DAYS_OF_WEEK["saturday"]
    assert parsed_sat.date() == datetime(2026, 10, 24).date()

    # "Monday" (next Monday)
    parsed_mon = parse_due_date("next monday", now_utc)
    assert parsed_mon is not None
    assert parsed_mon.weekday() == DAYS_OF_WEEK["monday"]
    assert parsed_mon.date() == datetime(2026, 10, 26).date()

    # Same day "Friday" -> schedules 7 days ahead
    parsed_fri = parse_due_date("friday", now_utc)
    assert parsed_fri is not None
    assert parsed_fri.date() == datetime(2026, 10, 30).date()


def test_parse_due_date_calendar_dates() -> None:
    now_utc = datetime(2026, 10, 23, 10, 0, 0, tzinfo=ZoneInfo("UTC"))

    # "November 15"
    parsed_nov = parse_due_date("November 15", now_utc)
    assert parsed_nov is not None
    assert parsed_nov.month == 11
    assert parsed_nov.day == 15
    assert parsed_nov.year == 2026

    # "Nov 15th"
    parsed_nov_th = parse_due_date("Nov 15th", now_utc)
    assert parsed_nov_th is not None
    assert parsed_nov_th.month == 11
    assert parsed_nov_th.day == 15

    # "on the 25th" (later this month)
    parsed_25 = parse_due_date("on the 25th", now_utc)
    assert parsed_25 is not None
    assert parsed_25.month == 10
    assert parsed_25.day == 25

    # "on the 10th" (past this month -> rolls over to next month)
    parsed_10 = parse_due_date("on the 10th", now_utc)
    assert parsed_10 is not None
    assert parsed_10.month == 11
    assert parsed_10.day == 10


def test_parse_due_date_invalid_raises_error() -> None:
    now_utc = datetime(2026, 10, 23, 10, 0, 0, tzinfo=ZoneInfo("UTC"))

    with pytest.raises(InvalidInputError) as exc_info:
        parse_due_date("someday next year maybe", now_utc)
    assert "Could not parse due date" in str(exc_info.value)

    with pytest.raises(InvalidInputError) as exc_info_feb:
        parse_due_date("February 31", now_utc)
    assert "Invalid date" in str(exc_info_feb.value)


def test_format_tasks_spoken() -> None:
    user_tz = ZoneInfo("UTC")

    # Empty list
    spoken_empty = format_tasks_spoken([], list_name="inbox")
    assert spoken_empty == "You have no pending tasks in your inbox list."

    # 1 task
    due = datetime(2026, 10, 24, 9, 0, 0, tzinfo=user_tz)
    tasks = [
        {
            "title": "Submit quarterly report",
            "due_at": due,
            "priority": "high",
            "list_name": "inbox",
        }
    ]
    spoken_single = format_tasks_spoken(tasks, user_tz=user_tz)
    assert "Submit quarterly report" in spoken_single
    assert "high priority" in spoken_single
    assert len(spoken_single) <= 300
    assert "*" not in spoken_single
    assert "#" not in spoken_single

    # Multiple tasks
    tasks.extend(
        [
            {"title": "Schedule dentist appointment", "due_at": None, "priority": "medium"},
            {"title": "Review team pull requests", "due_at": None, "priority": "low"},
        ]
    )
    spoken_multi = format_tasks_spoken(tasks, user_tz=user_tz)
    assert "You have 3 pending tasks" in spoken_multi
    assert "Submit quarterly report" in spoken_multi
    assert len(spoken_multi) <= 300


def test_task_enums() -> None:
    assert TaskPriority.HIGH.value == "high"
    assert TaskPriority.MEDIUM.value == "medium"
    assert TaskPriority.LOW.value == "low"

    assert TaskStatus.PENDING.value == "pending"
    assert TaskStatus.COMPLETED.value == "completed"
    assert TaskStatus.CANCELLED.value == "cancelled"
