"""Domain models and voice formatting for cross-module weekly review (T13.2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class WeeklyStudyStats:
    """Aggregated learning progress over the past 7 days."""

    quizzes_completed: int = 0
    questions_answered: int = 0
    accuracy_pct: float = 0.0
    streak_days: int = 0
    is_streak_record: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "quizzes_completed": self.quizzes_completed,
            "questions_answered": self.questions_answered,
            "accuracy_pct": self.accuracy_pct,
            "streak_days": self.streak_days,
            "is_streak_record": self.is_streak_record,
        }


@dataclass(frozen=True)
class WeeklyHabitStats:
    """Aggregated habit progress over the past 7 days."""

    active_count: int = 0
    completions_count: int = 0
    top_habit: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "active_count": self.active_count,
            "completions_count": self.completions_count,
            "top_habit": self.top_habit,
        }


@dataclass(frozen=True)
class WeeklyFinanceStats:
    """Aggregated personal expenditure over the past 7 days."""

    total_spent_minor: int = 0
    currency: str = "INR"

    @property
    def formatted_units(self) -> str:
        major = self.total_spent_minor // 100
        return f"{major:,}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_spent_minor": self.total_spent_minor,
            "currency": self.currency,
            "formatted": f"{self.currency} {self.formatted_units}",
        }


@dataclass(frozen=True)
class WeeklyHealthStats:
    """Aggregated health and wellness metrics over the past 7 days."""

    workouts_count: int = 0
    avg_daily_water_ml: int = 0
    active_days: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "workouts_count": self.workouts_count,
            "avg_daily_water_ml": self.avg_daily_water_ml,
            "active_days": self.active_days,
        }


@dataclass(frozen=True)
class WeeklyReviewSummary:
    """Full unified cross-module weekly report."""

    enabled_modules: list[str] = field(default_factory=list)
    study: WeeklyStudyStats | None = None
    habits: WeeklyHabitStats | None = None
    finance: WeeklyFinanceStats | None = None
    health: WeeklyHealthStats | None = None
    highlights: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "period": "weekly",
            "enabled_modules": list(self.enabled_modules),
            "study": self.study.to_dict() if self.study else None,
            "habits": self.habits.to_dict() if self.habits else None,
            "finance": self.finance.to_dict() if self.finance else None,
            "health": self.health.to_dict() if self.health else None,
            "highlights": list(self.highlights),
        }


def format_weekly_review_spoken(summary: WeeklyReviewSummary) -> str:
    """Format an adaptive, voice-first weekly summary strictly <= 300 chars without symbols."""
    clauses: list[str] = []

    # 1. Study summary
    if summary.study is not None and (
        summary.study.quizzes_completed > 0 or summary.study.streak_days > 0
    ):
        q_count = summary.study.quizzes_completed
        if q_count > 0:
            q_text = f"{q_count} quiz" if q_count == 1 else f"{q_count} quizzes"
            acc = round(summary.study.accuracy_pct)
            clauses.append(f"completed {q_text} with {acc}% accuracy")
        elif summary.study.streak_days > 0:
            clauses.append(f"maintained a {summary.study.streak_days} day study streak")

    # 2. Habit summary
    if summary.habits is not None and summary.habits.completions_count > 0:
        c_count = summary.habits.completions_count
        h_text = f"{c_count} habit session" if c_count == 1 else f"{c_count} habit sessions"
        clauses.append(f"logged {h_text}")

    # 3. Finance summary
    if summary.finance is not None and summary.finance.total_spent_minor > 0:
        clauses.append(f"spent {summary.finance.formatted_units} {summary.finance.currency}")

    # 4. Health summary
    if summary.health is not None and summary.health.workouts_count > 0:
        w_count = summary.health.workouts_count
        w_text = f"{w_count} workout" if w_count == 1 else f"{w_count} workouts"
        clauses.append(f"logged {w_text}")

    if not clauses:
        return (
            "No activity recorded this week yet. You can study with a quiz, "
            "track a habit, or log your expenses to see them here."
        )

    # Join clauses smoothly
    if len(clauses) == 1:
        body = clauses[0]
    elif len(clauses) == 2:
        body = f"{clauses[0]} and {clauses[1]}"
    else:
        body = ", ".join(clauses[:-1]) + f", and {clauses[-1]}"

    text = f"This week: You {body}."

    # Add optional highlight if space permits
    if summary.highlights:
        highlight = summary.highlights[0]
        candidate = f"{text} Highlight: {highlight}!"
        if len(candidate) <= 300:
            return candidate

    if len(text) > 300:
        text = text[:297] + "..."
    return text
