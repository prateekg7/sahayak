"""Unit and property tests for chores domain logic (T9.3)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from hypothesis import given
from hypothesis import strategies as st

from sahayak.core.errors import InvalidInputError
from sahayak.modules.home.domain.chores import (
    compute_next_chore_turn,
    compute_next_due_date,
    format_chore_added_spoken,
    format_chore_completed_spoken,
    format_chores_list_spoken,
    format_whose_turn_spoken,
    normalize_chore_title,
    normalize_frequency,
)


def test_normalize_chore_title_valid() -> None:
    assert normalize_chore_title("  do the dishes  ") == "Do The Dishes"
    assert normalize_chore_title("vacuum living room") == "Vacuum Living Room"


def test_normalize_chore_title_invalid() -> None:
    with pytest.raises(InvalidInputError, match="cannot be empty"):
        normalize_chore_title("   ")
    with pytest.raises(InvalidInputError, match="cannot exceed 256 characters"):
        normalize_chore_title("a" * 257)


def test_normalize_frequency() -> None:
    assert normalize_frequency(None) == "weekly"
    assert normalize_frequency("") == "weekly"
    assert normalize_frequency("DAILY") == "daily"
    assert normalize_frequency("Biweekly") == "biweekly"
    assert normalize_frequency("Monthly") == "monthly"
    with pytest.raises(InvalidInputError, match="Invalid frequency"):
        normalize_frequency("hourly")


def test_compute_next_due_date() -> None:
    base = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
    assert (compute_next_due_date("daily", base) - base).days == 1
    assert (compute_next_due_date("weekly", base) - base).days == 7
    assert (compute_next_due_date("biweekly", base) - base).days == 14
    assert (compute_next_due_date("monthly", base) - base).days == 30


@given(
    members=st.lists(
        st.text(min_size=1, max_size=16).filter(lambda s: bool(s.strip())),
        min_size=2,
        max_size=6,
        unique=True,
    ),
    rotations=st.integers(min_value=1, max_value=200),
)
def test_fairness_property_round_robin_rotation(members: list[str], rotations: int) -> None:
    """Fairness property: in N rounds across K members, turn counts differ by at most 1."""
    counts = {m.strip(): 0 for m in members}
    idx = 0
    for _ in range(rotations):
        assigned, idx = compute_next_chore_turn(members, idx)
        assert assigned is not None
        counts[assigned] += 1

    max_c = max(counts.values())
    min_c = min(counts.values())
    diff = max_c - min_c
    assert diff <= 1, f"Unfair rotation: max={max_c}, min={min_c} with {len(members)} members"


def test_spoken_formatting_voice_rules() -> None:
    added = format_chore_added_spoken("Dishes", "Alice", "weekly")
    assert len(added) <= 300
    assert "*" not in added and "#" not in added and "`" not in added
    assert "Dishes" in added and "Alice" in added

    due = datetime(2026, 11, 8, 10, 0, tzinfo=UTC)
    whose = format_whose_turn_spoken("Dishes", "Bob", due)
    assert len(whose) <= 300
    assert "Bob" in whose and "Dishes" in whose

    completed = format_chore_completed_spoken("Dishes", "Charlie")
    assert len(completed) <= 300
    assert "Dishes" in completed and "Charlie" in completed

    chores_list = format_chores_list_spoken(
        [
            {"title": "Dishes", "assigned_name": "Alice"},
            {"title": "Vacuuming", "assigned_name": "Bob"},
            {"title": "Mowing", "assigned_name": None},
        ]
    )
    assert len(chores_list) <= 300
    assert "You have 3 chores" in chores_list
