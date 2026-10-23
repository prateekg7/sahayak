"""Unit tests for habit domain rules, streak calculations, and speech formatting (T5.2)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sahayak.modules.productivity.domain.habits import (
    calculate_streak,
    format_habit_logged_spoken,
    format_habits_list_spoken,
    resolve_local_date,
)


def test_calculate_streak_empty() -> None:
    today = date(2026, 10, 23)
    curr, longest = calculate_streak([], today)
    assert curr == 0
    assert longest == 0


def test_calculate_streak_logged_today() -> None:
    today = date(2026, 10, 23)
    curr, longest = calculate_streak([today], today)
    assert curr == 1
    assert longest == 1


def test_calculate_streak_consecutive_days() -> None:
    today = date(2026, 10, 23)
    # 5 consecutive days: 19, 20, 21, 22, 23
    dates = [today - timedelta(days=i) for i in range(5)]
    curr, longest = calculate_streak(dates, today)
    assert curr == 5
    assert longest == 5


def test_calculate_streak_logged_yesterday_not_yet_today() -> None:
    today = date(2026, 10, 23)
    yesterday = today - timedelta(days=1)
    # Active streak still holds from yesterday
    dates = [yesterday, yesterday - timedelta(days=1), yesterday - timedelta(days=2)]
    curr, longest = calculate_streak(dates, today)
    assert curr == 3
    assert longest == 3


def test_calculate_streak_missed_day_breaks_current() -> None:
    today = date(2026, 10, 23)
    # Logged 2 days ago, missed yesterday and today
    dates = [today - timedelta(days=2), today - timedelta(days=3), today - timedelta(days=4)]
    curr, longest = calculate_streak(dates, today)
    assert curr == 0
    assert longest == 3  # Longest preserved


def test_calculate_streak_same_day_duplicates() -> None:
    today = date(2026, 10, 23)
    # Logged 3 times today and twice yesterday
    dates = [today, today, today, today - timedelta(days=1), today - timedelta(days=1)]
    curr, longest = calculate_streak(dates, today)
    assert curr == 2
    assert longest == 2


def test_calculate_streak_recovers_after_break() -> None:
    today = date(2026, 10, 23)
    # Historical 7-day streak, 10 days gap, then new 2-day streak today + yesterday
    old_dates = [today - timedelta(days=20 + i) for i in range(7)]
    recent_dates = [today, today - timedelta(days=1)]
    curr, longest = calculate_streak(old_dates + recent_dates, today)
    assert curr == 2
    assert longest == 7


def test_resolve_local_date_across_timezones() -> None:
    # 2026-10-23 23:30 UTC
    dt_utc = datetime(2026, 10, 23, 23, 30, 0, tzinfo=ZoneInfo("UTC"))

    # In New York (EDT, UTC-4), it is still 2026-10-23 19:30
    ny_date = resolve_local_date(dt_utc, "America/New_York")
    assert ny_date == date(2026, 10, 23)

    # In Tokyo (JST, UTC+9), it is already 2026-10-24 08:30
    tokyo_date = resolve_local_date(dt_utc, "Asia/Tokyo")
    assert tokyo_date == date(2026, 10, 24)


def test_format_habit_logged_spoken() -> None:
    spoken_1 = format_habit_logged_spoken("meditation", 1)
    assert "Logged meditation for today" in spoken_1
    assert "Streak started" in spoken_1

    spoken_5 = format_habit_logged_spoken("running", 5, is_new_record=True)
    assert "5 day streak" in spoken_5
    assert "new personal record" in spoken_5


def test_format_habits_list_spoken() -> None:
    spoken_empty = format_habits_list_spoken([])
    assert "You have no habits tracked yet" in spoken_empty

    habits = [
        {"name": "Read", "streak_current": 12},
        {"name": "Exercise", "streak_current": 3},
        {"name": "Floss", "streak_current": 0},
    ]
    spoken_list = format_habits_list_spoken(habits)
    assert "3 active habits" in spoken_list
    assert "Read with a 12 day streak" in spoken_list
    assert len(spoken_list) <= 300
