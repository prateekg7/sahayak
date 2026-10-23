"""Pure domain functions for academic quiz scoring and lifecycle transitions."""

from __future__ import annotations

from datetime import datetime


def evaluate_answer(correct_key: str, selected_key: str | None) -> bool:
    """Evaluate whether a student's selected answer key is correct.

    Comparison is case-insensitive and stripped of whitespace.
    """
    if selected_key is None or not selected_key.strip():
        return False
    return selected_key.strip().upper() == correct_key.strip().upper()


def calculate_quiz_score_percentage(score_correct: int, total: int) -> float:
    """Compute quiz percentage score bounded between 0.0 and 100.0."""
    if total <= 0:
        return 0.0
    percentage = (score_correct / total) * 100.0
    return round(min(100.0, max(0.0, percentage)), 1)


def is_quiz_finished(current_index: int, total: int) -> bool:
    """Determine whether all questions in a quiz have been answered."""
    return current_index >= total


def is_quiz_expired(expires_at: datetime, current_time: datetime) -> bool:
    """Check if quiz session has expired beyond its configured expiry timestamp."""
    return current_time >= expires_at
