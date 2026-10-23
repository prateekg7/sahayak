"""Pure domain models, streak calculation, and speech formatters for habits (T5.2)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Any
from zoneinfo import ZoneInfo


class HabitFrequency(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"


def calculate_streak(
    logged_dates: list[date],
    reference_date: date,
    grace_days: int = 0,
) -> tuple[int, int]:
    """Calculate current and longest consecutive daily streaks.

    Args:
        logged_dates: List of dates the habit was completed (unordered, may contain duplicates).
        reference_date: The active 'today' date in the user's timezone.
        grace_days: Allowed gap in days before breaking streak (default 0).

    Returns:
        tuple[int, int]: (current_streak, longest_streak).
    """
    if not logged_dates:
        return 0, 0

    unique_dates = sorted(set(logged_dates))
    date_set = set(unique_dates)

    # 1. Calculate longest streak across history
    longest = 0
    current_run = 0
    prev_d: date | None = None

    for d in unique_dates:
        if prev_d is None:
            current_run = 1
        elif (d - prev_d).days == 1 or (d - prev_d).days <= (1 + grace_days):
            current_run += 1
        else:
            current_run = 1
        if current_run > longest:
            longest = current_run
        prev_d = d

    # 2. Calculate current active streak ending today or yesterday
    current_streak = 0
    check_date = reference_date

    # If not logged today, check if active up to yesterday
    if check_date not in date_set:
        check_date = reference_date - timedelta(days=1)
        if check_date not in date_set:
            return 0, longest

    # Walk backwards counting consecutive days
    while check_date in date_set:
        current_streak += 1
        check_date -= timedelta(days=1)

    if current_streak > longest:
        longest = current_streak

    return current_streak, longest


def resolve_local_date(reference_dt: datetime, timezone_str: str = "UTC") -> date:
    """Resolve local date from UTC datetime in user's timezone."""
    try:
        tz = ZoneInfo(timezone_str)
    except Exception:
        tz = ZoneInfo("UTC")
    return reference_dt.astimezone(tz).date()


def format_habit_logged_spoken(
    name: str,
    streak: int,
    is_new_record: bool = False,
) -> str:
    """Produce concise spoken feedback when a habit is logged."""
    if streak <= 1:
        return f"Logged {name} for today. Streak started!"

    spoken = f"Logged {name} for today. You are on a {streak} day streak!"
    if is_new_record:
        spoken += " That is a new personal record!"
    return spoken


def format_habits_list_spoken(habits: list[dict[str, Any]]) -> str:
    """Produce concise spoken summary of habits and current streaks."""
    if not habits:
        return "You have no habits tracked yet. Say add a habit to start."

    count = len(habits)
    items: list[str] = []
    for h in habits[:4]:
        name = h.get("name", "Habit")
        streak = h.get("streak_current", 0)
        if streak > 0:
            items.append(f"{name} with a {streak} day streak")
        else:
            items.append(f"{name}")

    joined = ", ".join(items)
    summary = f"You have {count} active habit{'s' if count > 1 else ''}: {joined}."
    if count > 4:
        summary += f" And {count - 4} more."

    # Cap spoken summary
    if len(summary) > 300:
        summary = summary[:296] + "..."
    return summary
