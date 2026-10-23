"""Domain logic, duration validation, and time calculations for focus timer (T5.4)."""

from __future__ import annotations

from datetime import datetime

from sahayak.core.errors import InvalidInputError

MIN_DURATION_MINUTES = 1
MAX_DURATION_MINUTES = 180
DEFAULT_DURATION_MINUTES = 25


def validate_duration_minutes(duration: int | None) -> int:
    """Validate requested focus duration in minutes."""
    if duration is None:
        return DEFAULT_DURATION_MINUTES
    if duration < MIN_DURATION_MINUTES or duration > MAX_DURATION_MINUTES:
        raise InvalidInputError(
            f"Focus duration must be between {MIN_DURATION_MINUTES} and "
            f"{MAX_DURATION_MINUTES} minutes (got {duration})"
        )
    return duration


def calculate_session_remaining(
    planned_end_at: datetime,
    now: datetime,
    status: str,
) -> tuple[int, bool, bool]:
    """Calculate remaining seconds and whether session is active or should be completed.

    Returns:
        tuple[int, bool, bool]: (remaining_seconds, is_active, should_mark_completed).
    """
    if status != "active":
        return 0, False, False

    diff = (planned_end_at - now).total_seconds()
    if diff <= 0:
        return 0, False, True

    return int(diff), True, False


def format_session_start_spoken(duration_minutes: int, task_label: str | None) -> str:
    """Format voice summary for session start."""
    label_part = f" for {task_label.strip()}" if task_label and task_label.strip() else ""
    return (
        f"Started a {duration_minutes} minute focus session{label_part}. "
        "Ask me how much time is left anytime."
    )


def format_session_status_spoken(
    remaining_seconds: int,
    duration_minutes: int,
    task_label: str | None,
    is_completed: bool,
) -> str:
    """Format voice summary for session status query."""
    label_part = f" for {task_label.strip()}" if task_label and task_label.strip() else ""
    if is_completed:
        return (
            f"Your {duration_minutes} minute focus session{label_part} "
            "is finished. Great job staying focused."
        )

    remaining_minutes = (remaining_seconds + 59) // 60
    if remaining_minutes <= 1:
        return f"You have less than 1 minute remaining on your focus session{label_part}."
    return f"You have {remaining_minutes} minutes remaining on your focus session{label_part}."


def format_session_stop_spoken(elapsed_minutes: int, task_label: str | None) -> str:
    """Format voice summary when stopping a session."""
    label_part = f" for {task_label.strip()}" if task_label and task_label.strip() else ""
    if elapsed_minutes <= 0:
        return f"Focus session{label_part} stopped."
    return f"Focus session{label_part} stopped after {elapsed_minutes} minutes."


def format_history_spoken(total_sessions: int, total_minutes: int, today_sessions: int) -> str:
    """Format voice summary for focus history."""
    if total_sessions == 0:
        return "You have not completed any focus sessions yet. Say start a focus session to begin."
    session_word = "session" if total_sessions == 1 else "sessions"
    today_word = "session" if today_sessions == 1 else "sessions"
    return (
        f"You have completed {total_sessions} focus {session_word} totaling "
        f"{total_minutes} minutes. Today you completed {today_sessions} {today_word}."
    )
