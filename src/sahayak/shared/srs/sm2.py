"""SuperMemo-2 (SM-2) spaced repetition scheduling algorithm."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

MIN_EASE_FLOOR: float = 1.30
DEFAULT_EASE: float = 2.50


class ReviewRating(StrEnum):
    """User response rating when reviewing a flashcard."""

    AGAIN = "again"
    HARD = "hard"
    GOOD = "good"
    EASY = "easy"


@dataclass(frozen=True)
class SM2Result:
    """Outcome of applying the SM-2 interval and ease calculation."""

    ease: float
    interval_days: int
    repetitions: int


def calculate_sm2(
    rating: ReviewRating | str,
    ease: float = DEFAULT_EASE,
    interval_days: int = 0,
    repetitions: int = 0,
) -> SM2Result:
    """Calculate the next interval, ease factor, and repetition count per SM-2.

    Args:
        rating: Review feedback ('again', 'hard', 'good', 'easy').
        ease: Current ease factor (defaults to 2.5, clamped to minimum floor 1.3).
        interval_days: Current review interval in days.
        repetitions: Number of consecutive successful recall reviews.

    Returns:
        SM2Result with updated ease, interval_days, and repetitions.

    Raises:
        ValueError: If rating is unrecognized.
    """
    if isinstance(rating, str):
        try:
            rating_enum = ReviewRating(rating.lower().strip())
        except ValueError as exc:
            msg = f"Invalid rating '{rating}'. Expected one of: again, hard, good, easy."
            raise ValueError(msg) from exc
    else:
        rating_enum = rating

    # Ensure baseline ease respects the floor
    current_ease = max(MIN_EASE_FLOOR, ease)

    # 1. Update Ease Factor based on quality grade
    # again: -0.20, hard: -0.15, good: 0.00, easy: +0.15
    delta_map: dict[ReviewRating, float] = {
        ReviewRating.AGAIN: -0.20,
        ReviewRating.HARD: -0.15,
        ReviewRating.GOOD: 0.00,
        ReviewRating.EASY: +0.15,
    }
    next_ease = max(MIN_EASE_FLOOR, round(current_ease + delta_map[rating_enum], 2))

    # 2. Update Interval and Repetitions
    if rating_enum == ReviewRating.AGAIN:
        next_repetitions = 0
        next_interval = 1
    else:
        next_repetitions = repetitions + 1
        if next_repetitions == 1:
            next_interval = 1
        elif next_repetitions == 2:
            if rating_enum == ReviewRating.HARD:
                next_interval = 3
            elif rating_enum == ReviewRating.GOOD:
                next_interval = 6
            else:  # EASY
                next_interval = 8
        else:
            if rating_enum == ReviewRating.HARD:
                next_interval = max(interval_days + 1, round(interval_days * 1.2))
            elif rating_enum == ReviewRating.GOOD:
                next_interval = max(interval_days + 1, round(interval_days * next_ease))
            else:  # EASY
                next_interval = max(interval_days + 1, round(interval_days * next_ease * 1.3))

    return SM2Result(
        ease=next_ease,
        interval_days=next_interval,
        repetitions=next_repetitions,
    )
