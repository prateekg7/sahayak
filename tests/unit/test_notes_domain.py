"""Unit tests for notes domain logic and speech chunking (T5.3)."""

from __future__ import annotations

import pytest

from sahayak.core.errors import InvalidInputError
from sahayak.modules.productivity.domain.notes import (
    MAX_NOTE_LENGTH,
    chunk_note_for_speech,
    clean_note_text,
    format_search_results_spoken,
)


def test_clean_note_text_valid() -> None:
    text = "  Buy groceries: milk, eggs, bread  "
    clean = clean_note_text(text)
    assert clean == "Buy groceries: milk, eggs, bread"


def test_clean_note_text_empty() -> None:
    with pytest.raises(InvalidInputError, match="cannot be empty"):
        clean_note_text("   ")


def test_clean_note_text_too_long() -> None:
    too_long = "a" * (MAX_NOTE_LENGTH + 1)
    with pytest.raises(InvalidInputError, match="exceeds maximum length"):
        clean_note_text(too_long)


def test_chunk_note_for_speech_short() -> None:
    short_text = "Quick reminder to call mom."
    spoken, has_more = chunk_note_for_speech(short_text, max_chars=240)
    assert spoken == short_text
    assert has_more is False


def test_chunk_note_for_speech_long() -> None:
    long_text = (
        "First sentence explaining meeting notes. Second sentence with action items. "
        "Third sentence outlining follow up steps for engineering team. "
        "Fourth sentence detailing timeline and budget requirements for next quarter release."
    )
    spoken, has_more = chunk_note_for_speech(long_text, max_chars=120)
    assert has_more is True
    assert spoken.endswith("... Ask me to read more to continue.")
    assert len(spoken) <= 150
    # Clean boundary
    assert not spoken.startswith("...")


def test_format_search_results_spoken_empty() -> None:
    spoken = format_search_results_spoken("groceries", [])
    assert spoken == "I could not find any notes matching groceries."
    assert len(spoken) <= 300


def test_format_search_results_spoken_single() -> None:
    notes = [{"content": "Buy almond milk and sourdough bread from the bakery."}]
    spoken = format_search_results_spoken("bread", notes)
    assert "Found 1 note for bread:" in spoken
    assert len(spoken) <= 300


def test_format_search_results_spoken_multiple() -> None:
    notes = [
        {"content": "Note 1 about project architecture and design."},
        {"content": "Note 2 about project timelines and deliverables."},
        {"content": "Note 3 about project risks and mitigations."},
    ]
    spoken = format_search_results_spoken("project", notes)
    assert "Found 3 notes matching project." in spoken
    assert "And 1 more." in spoken
    assert len(spoken) <= 300
