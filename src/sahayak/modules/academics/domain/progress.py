"""Pure domain logic for study streaks, weak topic ranking, and progress summaries (T3.13).

Rules:
- Strictly pure: imports no database, I/O, or framework libraries.
- User timezone-aware date resolution for accurate calendar streak tracking.
- Voice summary generation respecting SPOKEN_SUMMARY_MAX_CHARS (<= 300 chars).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True)
class StreakInfo:
    """Calculated streak metrics in user's calendar days."""

    current_streak: int
    longest_streak: int
    studied_today: bool
    last_active_date: date | None


@dataclass(frozen=True)
class TopicStatSummary:
    """Normalized performance summary for a single topic."""

    topic: str
    attempts: int
    correct: int
    accuracy_pct: float


@dataclass(frozen=True)
class WeeklySummary:
    """Summary of student activities in the past 7 days."""

    active_days: int
    quizzes_completed: int
    questions_answered: int
    correct_count: int
    accuracy_pct: float
    cards_reviewed: int


def timestamps_to_dates(
    timestamps: Iterable[datetime],
    user_timezone: str = "UTC",
) -> set[date]:
    """Convert UTC datetimes into localized calendar dates.

    Args:
        timestamps: Collection of UTC activity timestamps.
        user_timezone: IANA timezone string (falls back to UTC if invalid).

    Returns:
        Set of localized date objects.
    """
    try:
        tz = ZoneInfo(user_timezone)
    except (ZoneInfoNotFoundError, ValueError):
        tz = ZoneInfo("UTC")

    dates: set[date] = set()
    for ts in timestamps:
        if ts.tzinfo is None:
            # Assume UTC if naive
            localized_ts = ts.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz)
        else:
            localized_ts = ts.astimezone(tz)
        dates.add(localized_ts.date())
    return dates


def calculate_streak(
    activity_dates: Iterable[date],
    today: date,
) -> StreakInfo:
    """Compute current and longest streak in calendar days relative to today.

    Behavior:
    - Activity on 'today' increments/maintains the streak and sets studied_today=True.
    - If no activity today, but activity occurred 'yesterday', the streak is still active
      (giving the user until the end of today to preserve it), but studied_today=False.
    - If no activity today and no activity yesterday, current_streak is 0.
    - Longest streak counts the maximum run of consecutive calendar days across all history.
    """
    unique_dates = {d for d in activity_dates if d <= today}
    if not unique_dates:
        return StreakInfo(
            current_streak=0,
            longest_streak=0,
            studied_today=False,
            last_active_date=None,
        )

    sorted_dates = sorted(unique_dates)
    last_active = sorted_dates[-1]
    studied_today = today in unique_dates

    # 1. Calculate current streak
    current_streak = 0
    if studied_today:
        check_date = today
        while check_date in unique_dates:
            current_streak += 1
            check_date -= timedelta(days=1)
    elif (today - timedelta(days=1)) in unique_dates:
        check_date = today - timedelta(days=1)
        while check_date in unique_dates:
            current_streak += 1
            check_date -= timedelta(days=1)
    else:
        current_streak = 0

    # 2. Calculate longest streak
    longest_streak = 0
    run = 0
    prev_date: date | None = None

    for d in sorted_dates:
        if prev_date is None:
            run = 1
        elif d == prev_date + timedelta(days=1):
            run += 1
        else:
            run = 1
        prev_date = d
        if run > longest_streak:
            longest_streak = run

    return StreakInfo(
        current_streak=current_streak,
        longest_streak=max(longest_streak, current_streak),
        studied_today=studied_today,
        last_active_date=last_active,
    )


def calculate_weak_topics(
    stats: list[TopicStatSummary],
    min_attempts: int = 1,
    threshold_pct: float = 75.0,
) -> list[TopicStatSummary]:
    """Rank topics needing reinforcement, ordered from lowest to highest accuracy.

    Args:
        stats: Aggregated topic performance list.
        min_attempts: Minimum questions attempted to consider for weakness.
        threshold_pct: Topics with accuracy <= threshold_pct are classified as weak.
    """
    eligible = [s for s in stats if s.attempts >= min_attempts and s.accuracy_pct <= threshold_pct]
    # Sort lowest accuracy first; on tie, more attempts first; on tie, topic name
    return sorted(eligible, key=lambda s: (s.accuracy_pct, -s.attempts, s.topic.lower()))


def calculate_weekly_summary(
    activity_dates: Iterable[date],
    today: date,
    quizzes_completed: int,
    questions_answered: int,
    correct_count: int,
    cards_reviewed: int,
) -> WeeklySummary:
    """Summarize student learning engagement across the 7-day window ending on today."""
    seven_days_ago = today - timedelta(days=6)
    active_days = len({d for d in activity_dates if seven_days_ago <= d <= today})

    accuracy_pct = (
        round((correct_count / questions_answered) * 100.0, 1) if questions_answered > 0 else 0.0
    )

    return WeeklySummary(
        active_days=active_days,
        quizzes_completed=quizzes_completed,
        questions_answered=questions_answered,
        correct_count=correct_count,
        accuracy_pct=accuracy_pct,
        cards_reviewed=cards_reviewed,
    )


# ---------------------------------------------------------------------------
# Spoken summary formatters (guaranteed <= 300 chars, no markdown/symbols)
# ---------------------------------------------------------------------------


def format_summary_spoken(
    quizzes_count: int,
    questions_count: int,
    accuracy_pct: float,
    streak_days: int,
    weakest_topic: str | None,
) -> str:
    """Create a concise, voice-friendly overall progress summary."""
    if quizzes_count == 0 and questions_count == 0:
        return (
            "You haven't completed any quizzes yet. Say 'quiz me on science' "
            "to get started and build your study streak!"
        )

    parts: list[str] = [
        f"You have answered {questions_count} questions with {accuracy_pct:.0f} percent accuracy "
        f"across {quizzes_count} {'quiz' if quizzes_count == 1 else 'quizzes'}."
    ]

    if streak_days > 0:
        parts.append(f"Your study streak is {streak_days} {'day' if streak_days == 1 else 'days'}.")

    if weakest_topic:
        parts.append(
            f"Your weakest topic is {weakest_topic}. Say 'quiz me on my weak topics' to practice."
        )

    spoken = " ".join(parts)
    return spoken[:295]


def format_weak_topics_spoken(weak_topics: list[TopicStatSummary]) -> str:
    """Create a voice-friendly weak topics summary."""
    if not weak_topics:
        return (
            "You don't have any weak topics right now! Great job keeping your accuracy high. "
            "Say 'quiz me on science' to continue learning."
        )

    top = weak_topics[0]
    spoken = (
        f"Your weakest topic is {top.topic} at {top.accuracy_pct:.0f} percent accuracy "
        f"across {top.attempts} questions."
    )

    if len(weak_topics) > 1:
        second = weak_topics[1]
        spoken += (
            f" Followed by {second.topic} at {second.accuracy_pct:.0f} percent. "
            f"Say 'quiz me on my weak topics' to practice."
        )
    else:
        spoken += " Say 'quiz me on my weak topics' to practice."

    return spoken[:295]


def format_streak_spoken(streak: StreakInfo) -> str:
    """Create a voice-friendly streak summary."""
    if streak.current_streak == 0 and streak.longest_streak == 0:
        return (
            "You don't have an active study streak yet. Complete a quiz today to start your streak!"
        )

    if streak.studied_today:
        spoken = (
            f"You are on a {streak.current_streak} day study streak, and you have already "
            f"studied today! Your best streak is {streak.longest_streak} days. Keep it up!"
        )
    elif streak.current_streak > 0:
        spoken = (
            f"You have a {streak.current_streak} day study streak! Complete a quiz or review "
            f"flashcards today to keep it going. Best streak: {streak.longest_streak} days."
        )
    else:
        spoken = (
            f"Your study streak reset, but your best streak is {streak.longest_streak} days. "
            f"Start a quiz today to begin a new streak!"
        )

    return spoken[:295]


def format_weekly_spoken(summary: WeeklySummary) -> str:
    """Create a voice-friendly 7-day weekly activity summary."""
    if summary.active_days == 0 and summary.quizzes_completed == 0 and summary.cards_reviewed == 0:
        return (
            "You haven't recorded any study sessions in the past 7 days. "
            "Say 'quiz me on science' or 'review flashcards' to get back on track!"
        )

    quiz_word = "quiz" if summary.quizzes_completed == 1 else "quizzes"
    card_word = "card" if summary.cards_reviewed == 1 else "cards"
    spoken = (
        f"In the past 7 days, you were active on {summary.active_days} of 7 days, "
        f"completed {summary.quizzes_completed} {quiz_word} "
        f"with {summary.accuracy_pct:.0f} percent accuracy, "
        f"and reviewed {summary.cards_reviewed} {card_word}."
    )
    return spoken[:295]
