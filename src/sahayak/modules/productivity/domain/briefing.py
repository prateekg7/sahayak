"""Domain formatting and assembly for the unified daily briefing (T5.5)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BriefingItems:
    """Aggregated elements for constructing a user's daily briefing."""

    tasks_due: list[str] = field(default_factory=list)
    habits_pending: list[str] = field(default_factory=list)
    academics_enabled: bool = False
    flashcards_due_count: int = 0
    study_tasks: list[str] = field(default_factory=list)
    study_streak: int = 0
    focus_today_completed: int = 0


def format_daily_briefing_spoken(items: BriefingItems) -> str:
    """Format a natural, spoken summary strictly under 300 characters without symbols."""
    sentences: list[str] = ["Good morning!"]

    # Tasks section
    num_tasks = len(items.tasks_due)
    if num_tasks == 0:
        sentences.append("You have no tasks due today.")
    elif num_tasks == 1:
        sentences.append(f"You have 1 task due today: {items.tasks_due[0]}.")
    else:
        task_preview = f"{items.tasks_due[0]} and {items.tasks_due[1]}"
        if num_tasks > 2:
            task_preview += f" plus {num_tasks - 2} more"
        sentences.append(f"You have {num_tasks} tasks due today: {task_preview}.")

    # Habits section
    num_habits = len(items.habits_pending)
    if num_habits == 1:
        sentences.append(f"You have 1 habit to complete: {items.habits_pending[0]}.")
    elif num_habits > 1:
        sentences.append(f"You have {num_habits} habits pending.")

    # Academics section (only when enabled)
    if items.academics_enabled:
        acad_parts: list[str] = []
        if items.flashcards_due_count > 0:
            card_word = "card" if items.flashcards_due_count == 1 else "cards"
            acad_parts.append(f"{items.flashcards_due_count} {card_word} due")
        if items.study_tasks:
            acad_parts.append(f"{len(items.study_tasks)} study tasks")
        if acad_parts:
            sentences.append(f"In academics, you have {' and '.join(acad_parts)}.")
        elif items.study_streak > 1:
            sentences.append(f"Your study streak is at {items.study_streak} days.")

    sentences.append("Have a productive day!")
    summary = " ".join(sentences)

    # If exceeding 300 characters, fallback to compact high-level summary
    if len(summary) > 290:
        compact = (
            f"Good morning! You have {num_tasks} tasks due today and {num_habits} habits pending."
        )
        if items.academics_enabled and items.flashcards_due_count > 0:
            compact += f" You also have {items.flashcards_due_count} flashcards to review."
        compact += " Have a productive day!"
        if len(compact) > 295:
            compact = compact[:292] + "..."
        return compact

    return summary
