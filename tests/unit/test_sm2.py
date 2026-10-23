"""Tests for the SM-2 spaced repetition algorithm (T3.9)."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from sahayak.shared.srs.sm2 import (
    DEFAULT_EASE,
    MIN_EASE_FLOOR,
    ReviewRating,
    calculate_sm2,
)

RATINGS = [ReviewRating.AGAIN, ReviewRating.HARD, ReviewRating.GOOD, ReviewRating.EASY]


def test_sm2_reference_table_progression() -> None:
    """Validate SM-2 progression against canonical reference table."""
    # Start: fresh card (ease=2.5, interval=0, reps=0)
    ease = DEFAULT_EASE
    interval = 0
    reps = 0

    # Review 1: Good -> interval: 1, ease: 2.50, reps: 1
    r1 = calculate_sm2("good", ease=ease, interval_days=interval, repetitions=reps)
    assert r1.interval_days == 1
    assert r1.ease == 2.50
    assert r1.repetitions == 1

    # Review 2: Good -> interval: 6, ease: 2.50, reps: 2
    r2 = calculate_sm2(
        "good", ease=r1.ease, interval_days=r1.interval_days, repetitions=r1.repetitions
    )
    assert r2.interval_days == 6
    assert r2.ease == 2.50
    assert r2.repetitions == 2

    # Review 3: Good -> interval: round(6 * 2.5) = 15, ease: 2.50, reps: 3
    r3 = calculate_sm2(
        "good", ease=r2.ease, interval_days=r2.interval_days, repetitions=r2.repetitions
    )
    assert r3.interval_days == 15
    assert r3.ease == 2.50
    assert r3.repetitions == 3

    # Review 4: Good -> interval: round(15 * 2.5) = 38, ease: 2.50, reps: 4
    r4 = calculate_sm2(
        "good", ease=r3.ease, interval_days=r3.interval_days, repetitions=r3.repetitions
    )
    assert r4.interval_days == 38
    assert r4.ease == 2.50
    assert r4.repetitions == 4

    # Review 5: Again (lapse) -> interval: 1, ease: 2.30 (-0.20), reps: 0
    r5 = calculate_sm2(
        "again", ease=r4.ease, interval_days=r4.interval_days, repetitions=r4.repetitions
    )
    assert r5.interval_days == 1
    assert r5.ease == 2.30
    assert r5.repetitions == 0

    # Review 6: Easy -> interval: 1, ease: 2.45 (+0.15), reps: 1
    r6 = calculate_sm2(
        "easy", ease=r5.ease, interval_days=r5.interval_days, repetitions=r5.repetitions
    )
    assert r6.interval_days == 1
    assert r6.ease == 2.45
    assert r6.repetitions == 1

    # Review 7: Easy -> interval: 8, ease: 2.60 (+0.15), reps: 2
    r7 = calculate_sm2(
        "easy", ease=r6.ease, interval_days=r6.interval_days, repetitions=r6.repetitions
    )
    assert r7.interval_days == 8
    assert r7.ease == 2.60
    assert r7.repetitions == 2

    # Review 8: Hard -> interval: round(8 * 1.2) = 10, ease: 2.45 (-0.15), reps: 3
    r8 = calculate_sm2(
        "hard", ease=r7.ease, interval_days=r7.interval_days, repetitions=r7.repetitions
    )
    assert r8.interval_days == 10
    assert r8.ease == 2.45
    assert r8.repetitions == 3


def test_sm2_invalid_rating_raises_value_error() -> None:
    """Invalid rating string raises ValueError."""
    with pytest.raises(ValueError, match="Invalid rating 'perfect'"):
        calculate_sm2("perfect")


@given(st.lists(st.sampled_from(RATINGS), min_size=1, max_size=50))
def test_sm2_property_ease_floor(ratings: list[ReviewRating]) -> None:
    """Property: Ease never drops below MIN_EASE_FLOOR (1.30) for any rating sequence."""
    ease = DEFAULT_EASE
    interval = 0
    reps = 0

    for r in ratings:
        res = calculate_sm2(r, ease=ease, interval_days=interval, repetitions=reps)
        assert res.ease >= MIN_EASE_FLOOR
        ease = res.ease
        interval = res.interval_days
        reps = res.repetitions


@given(
    st.sampled_from([ReviewRating.GOOD, ReviewRating.EASY]),
    st.floats(min_value=1.3, max_value=3.5),
    st.integers(min_value=1, max_value=365),
    st.integers(min_value=1, max_value=20),
)
def test_sm2_property_monotonic_intervals_for_good_and_easy(
    rating: ReviewRating,
    ease: float,
    current_interval: int,
    reps: int,
) -> None:
    """Property: Good and Easy ratings strictly increase review intervals
    for established cards (reps >= 1).
    """
    res = calculate_sm2(rating, ease=ease, interval_days=current_interval, repetitions=reps)
    if reps >= 2:
        assert res.interval_days > current_interval
    elif reps == 1:
        # From rep 1 to rep 2, intervals advance to 6 (Good) or 8 (Easy), which is > 1
        assert res.interval_days >= 6


@given(
    st.floats(min_value=0.5, max_value=5.0),
    st.integers(min_value=0, max_value=1000),
    st.integers(min_value=0, max_value=50),
)
def test_sm2_property_again_resets_repetitions_and_sets_interval_one(
    ease: float,
    interval: int,
    reps: int,
) -> None:
    """Property: 'again' rating unconditionally resets repetitions to 0 and interval to 1."""
    res = calculate_sm2("again", ease=ease, interval_days=interval, repetitions=reps)
    assert res.repetitions == 0
    assert res.interval_days == 1
    assert res.ease >= MIN_EASE_FLOOR
