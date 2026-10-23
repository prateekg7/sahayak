"""Unit tests for daily briefing domain formatting (T5.5)."""

from __future__ import annotations

from sahayak.modules.productivity.domain.briefing import (
    BriefingItems,
    format_daily_briefing_spoken,
)


def test_format_daily_briefing_all_items() -> None:
    items = BriefingItems(
        tasks_due=["Finish physics lab report", "Submit literature review"],
        habits_pending=["Morning Meditation"],
        academics_enabled=True,
        flashcards_due_count=4,
        study_tasks=["Chapter 3 Thermodynamics"],
        study_streak=5,
        focus_today_completed=1,
    )
    spoken = format_daily_briefing_spoken(items)
    assert "2 tasks due today:" in spoken
    assert "Finish physics lab report and Submit literature review" in spoken
    assert "1 habit to complete: Morning Meditation" in spoken
    assert "4 cards due and 1 study tasks" in spoken
    assert len(spoken) <= 300
    assert "'" not in spoken
    assert '"' not in spoken
    assert "#" not in spoken


def test_format_daily_briefing_academics_disabled() -> None:
    items = BriefingItems(
        tasks_due=["Call plumber"],
        habits_pending=["Drink 2L Water", "Read 10 pages"],
        academics_enabled=False,
    )
    spoken = format_daily_briefing_spoken(items)
    assert "1 task due today: Call plumber" in spoken
    assert "2 habits pending" in spoken
    assert "academics" not in spoken
    assert len(spoken) <= 300


def test_format_daily_briefing_empty() -> None:
    items = BriefingItems(
        tasks_due=[],
        habits_pending=[],
        academics_enabled=False,
    )
    spoken = format_daily_briefing_spoken(items)
    assert "You have no tasks due today" in spoken
    assert "Have a productive day!" in spoken
    assert len(spoken) <= 300


def test_format_daily_briefing_truncation_under_300_chars() -> None:
    many_tasks = [
        f"Very long detailed task description number {i} to test voice buffer" for i in range(10)
    ]
    items = BriefingItems(
        tasks_due=many_tasks,
        habits_pending=["Habit A", "Habit B", "Habit C"],
        academics_enabled=True,
        flashcards_due_count=20,
    )
    spoken = format_daily_briefing_spoken(items)
    assert len(spoken) <= 300
