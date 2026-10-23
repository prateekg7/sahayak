"""Unit and property tests for spoken answer matching and scoring (T3.5)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from sahayak.modules.academics.domain.answer_matching import (
    AnswerMatchResult,
    match_spoken_answer,
)
from sahayak.modules.academics.domain.scoring import (
    calculate_quiz_score_percentage,
    evaluate_answer,
    is_quiz_expired,
    is_quiz_finished,
)

STANDARD_OPTIONS = {
    "A": "Chlorophyll",
    "B": "Hemoglobin",
    "C": "Melanin",
    "D": "Carotene",
}


# Table of >= 60 diverse spoken-answer test cases covering letters, phrases,
# ordinals, numerals, ASR homophones, exact text, partial text, and ambiguity.
SPOKEN_ANSWER_TEST_CASES: list[tuple[str, str | None, bool]] = [
    # Explicit single letters (uppercase and lowercase)
    ("A", "A", False),
    ("a", "A", False),
    ("B", "B", False),
    ("b", "B", False),
    ("C", "C", False),
    ("c", "C", False),
    ("D", "D", False),
    ("d", "D", False),
    ("A.", "A", False),
    ("(B)", "B", False),
    # Explicit option phrases
    ("option A", "A", False),
    ("Option B", "B", False),
    ("choice C", "C", False),
    ("Choice D", "D", False),
    ("letter A", "A", False),
    ("letter B", "B", False),
    ("answer C", "C", False),
    ("answer D", "D", False),
    ("it is A", "A", False),
    ("it's B", "B", False),
    ("is it C", "C", False),
    ("my answer is option D", "D", False),
    ("I think it is choice A", "A", False),
    # Ordinals (1st to 4th)
    ("first", "A", False),
    ("1st", "A", False),
    ("the first one", "A", False),
    ("first option", "A", False),
    ("first choice", "A", False),
    ("second", "B", False),
    ("2nd", "B", False),
    ("the second one", "B", False),
    ("second option", "B", False),
    ("second choice", "B", False),
    ("third", "C", False),
    ("3rd", "C", False),
    ("the third one", "C", False),
    ("third option", "C", False),
    ("third choice", "C", False),
    ("fourth", "D", False),
    ("4th", "D", False),
    ("the fourth one", "D", False),
    ("fourth option", "D", False),
    ("fourth choice", "D", False),
    # Numerals (1 to 4)
    ("1", "A", False),
    ("one", "A", False),
    ("number 1", "A", False),
    ("option 1", "A", False),
    ("2", "B", False),
    ("two", "B", False),
    ("number 2", "B", False),
    ("option 2", "B", False),
    ("3", "C", False),
    ("three", "C", False),
    ("number 3", "C", False),
    ("option 3", "C", False),
    ("4", "D", False),
    ("four", "D", False),
    ("number 4", "D", False),
    ("option 4", "D", False),
    # Speech-to-text / ASR homophones
    ("ay", "A", False),
    ("eh", "A", False),
    ("be", "B", False),
    ("bee", "B", False),
    ("see", "C", False),
    ("sea", "C", False),
    ("dee", "D", False),
    ("won", "A", False),  # homophone for 1 / one
    ("to", "B", False),  # homophone for 2 / two
    ("too", "B", False),  # homophone for 2 / two
    ("for", "D", False),  # homophone for 4 / four
    ("fore", "D", False),  # homophone for 4 / four
    # Exact text matches
    ("Chlorophyll", "A", False),
    ("chlorophyll", "A", False),
    ("Hemoglobin", "B", False),
    ("hemoglobin", "B", False),
    ("Melanin", "C", False),
    ("melanin", "C", False),
    ("Carotene", "D", False),
    ("carotene", "D", False),
    # Fuzzy text matches
    ("chloro phyll", "A", False),
    ("hemo globin", "B", False),
    ("melanine", "C", False),
    ("caroten", "D", False),
    # Ambiguous cases (multiple options mentioned)
    ("A or B", None, True),
    ("is it B or C", None, True),
    ("A and D", None, True),
    # Unknown / Unmatched cases
    ("I don't know", None, False),
    ("pass", None, False),
    ("banana", None, False),
    ("quantum physics", None, False),
]


@pytest.mark.parametrize(
    ("utterance", "expected_key", "expected_ambiguous"),
    SPOKEN_ANSWER_TEST_CASES,
)
def test_spoken_answer_test_cases_table(
    utterance: str,
    expected_key: str | None,
    expected_ambiguous: bool,
) -> None:
    """Validate all >= 60 diverse spoken-answer test cases."""
    result = match_spoken_answer(utterance, STANDARD_OPTIONS)
    assert result.matched_key == expected_key, f"Failed on utterance: '{utterance}'"
    assert result.is_ambiguous == expected_ambiguous, f"Ambiguity mismatch on: '{utterance}'"


def test_empty_utterance_and_empty_options() -> None:
    """Empty inputs return graceful failure results."""
    res1 = match_spoken_answer("", STANDARD_OPTIONS)
    assert res1.matched_key is None
    assert not res1.is_ambiguous

    res2 = match_spoken_answer("   ", STANDARD_OPTIONS)
    assert res2.matched_key is None

    res3 = match_spoken_answer("A", {})
    assert res3.matched_key is None


def test_scoring_domain_functions() -> None:
    """Verify answer correctness and percentage scoring."""
    assert evaluate_answer("A", "A") is True
    assert evaluate_answer("A", "a") is True
    assert evaluate_answer("A", " B ") is False
    assert evaluate_answer("A", None) is False

    assert calculate_quiz_score_percentage(5, 5) == 100.0
    assert calculate_quiz_score_percentage(4, 5) == 80.0
    assert calculate_quiz_score_percentage(0, 5) == 0.0
    assert calculate_quiz_score_percentage(0, 0) == 0.0

    assert is_quiz_finished(5, 5) is True
    assert is_quiz_finished(4, 5) is False

    now = datetime.now(UTC)
    assert is_quiz_expired(now - timedelta(minutes=1), now) is True
    assert is_quiz_expired(now + timedelta(minutes=10), now) is False


# ---------------------------------------------------------------------------
# Hypothesis Property-Based Tests
# ---------------------------------------------------------------------------


@given(st.text(min_size=0, max_size=100))
def test_property_never_matches_multiple_options_simultaneously(utterance: str) -> None:
    """In all possible generated inputs, matched_key must be at most one option key or None."""
    result = match_spoken_answer(utterance, STANDARD_OPTIONS)
    assert isinstance(result, AnswerMatchResult)
    if result.matched_key is not None:
        assert result.matched_key in STANDARD_OPTIONS
        assert result.confidence > 0.0
        # If an option key is matched, it cannot simultaneously be marked ambiguous
        assert not result.is_ambiguous


@given(st.sampled_from(["A", "B", "C", "D"]))
def test_property_idempotence_on_option_matching(key: str) -> None:
    """Matching the exact text of an option is always deterministic and idempotent."""
    text_val = STANDARD_OPTIONS[key]
    res1 = match_spoken_answer(text_val, STANDARD_OPTIONS)
    res2 = match_spoken_answer(text_val, STANDARD_OPTIONS)
    assert res1 == res2
    assert res1.matched_key == key
    assert res1.confidence >= 95.0
