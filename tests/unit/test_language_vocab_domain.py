"""Unit and property tests for language vocabulary domain logic (T11.1)."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from sahayak.core.errors import InvalidInputError
from sahayak.modules.language.domain.languages import (
    DEFAULT_LANGUAGE,
    DEFAULT_LEVEL,
    normalize_language,
    normalize_level,
)
from sahayak.modules.language.domain.seeds import get_seed_words_for
from sahayak.modules.language.domain.vocab import (
    MAX_SPOKEN_CHARS,
    format_graded_spoken,
    format_review_card_spoken,
    format_stats_spoken,
    format_word_of_day_spoken,
    sanitize_spoken_text,
    validate_word_payload,
)


def test_language_normalization() -> None:
    """Validate language normalization, aliases, and error rejection."""
    assert normalize_language(None) == DEFAULT_LANGUAGE
    assert normalize_language("spanish") == "spanish"
    assert normalize_language("  es  ") == "spanish"
    assert normalize_language("ESPANOL") == "spanish"
    assert normalize_language("fr") == "french"
    assert normalize_language("Deutsch") == "german"
    assert normalize_language("nihongo") == "japanese"
    assert normalize_language("hi") == "hindi"

    with pytest.raises(InvalidInputError, match="Unsupported language 'klingon'"):
        normalize_language("klingon")


def test_level_normalization() -> None:
    """Validate level normalization, aliases, and error rejection."""
    assert normalize_level(None) == DEFAULT_LEVEL
    assert normalize_level("beginner") == "beginner"
    assert normalize_level("A1") == "beginner"
    assert normalize_level("b2") == "intermediate"
    assert normalize_level("hard") == "advanced"

    with pytest.raises(InvalidInputError, match="Unsupported proficiency level 'master'"):
        normalize_level("master")


def test_word_payload_validation() -> None:
    """Validate word creation payload constraints."""
    validate_word_payload("hola", "hello", "oh-lah")

    with pytest.raises(InvalidInputError, match="Word must not be empty"):
        validate_word_payload("", "hello", "oh-lah")

    with pytest.raises(InvalidInputError, match="Word exceeds 100 characters"):
        validate_word_payload("x" * 101, "hello", "oh-lah")

    with pytest.raises(InvalidInputError, match="Translation must not be empty"):
        validate_word_payload("hola", "", "oh-lah")

    with pytest.raises(InvalidInputError, match="Pronunciation hint must not be empty"):
        validate_word_payload("hola", "hello", "")


def test_seed_words_retrieval() -> None:
    """Verify curated seed vocabulary exists for supported languages."""
    for lang in ("spanish", "french", "german", "hindi", "japanese"):
        seeds = get_seed_words_for(lang)
        assert len(seeds) >= 2
        for s in seeds:
            assert s.language == lang
            assert s.word
            assert s.translation
            assert s.pronunciation_hint
            assert s.example_sentence
            assert s.example_translation


def test_spoken_summary_no_markdown_or_quotes() -> None:
    """Spoken output must never include markdown or quotes."""
    text = "Here is **bold**, *italic*, # header, `code`, and 'quotes' with \"double\"."
    cleaned = sanitize_spoken_text(text)
    assert "*" not in cleaned
    assert "#" not in cleaned
    assert "`" not in cleaned
    assert "'" not in cleaned
    assert '"' not in cleaned


def test_spoken_formatters_length_limits() -> None:
    """All spoken formatters must produce speech strictly within MAX_SPOKEN_CHARS."""
    spoken_wod = format_word_of_day_spoken(
        word="desarrollo",
        language="spanish",
        translation="development",
        pronunciation_hint="deh-sah-rroh-yoh",
        example_sentence="El desarrollo economico es muy importante para el pais.",
        example_translation="Economic development is very important for the country.",
        is_already_learned=False,
    )
    assert len(spoken_wod) <= MAX_SPOKEN_CHARS
    assert "desarrollo" in spoken_wod
    assert "development" in spoken_wod

    spoken_review = format_review_card_spoken(
        word="bonjour",
        language="french",
        pronunciation_hint="bohn-zhoor",
        remaining_count=3,
    )
    assert len(spoken_review) <= MAX_SPOKEN_CHARS
    assert "bonjour" in spoken_review

    spoken_graded = format_graded_spoken(
        word="gracias",
        rating="good",
        interval_days=6,
        translation="thank you",
    )
    assert len(spoken_graded) <= MAX_SPOKEN_CHARS
    assert "gracias" in spoken_graded
    assert "6 days" in spoken_graded

    spoken_stats = format_stats_spoken(
        language="spanish",
        total_learned=15,
        due_count=2,
        mastered_count=7,
    )
    assert len(spoken_stats) <= MAX_SPOKEN_CHARS
    assert "15 words" in spoken_stats


@given(
    word=st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll")),
        min_size=1,
        max_size=20,
    ),
    translation=st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Zs")),
        min_size=1,
        max_size=30,
    ),
    pronunciation=st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Zs")),
        min_size=1,
        max_size=30,
    ),
    days=st.integers(min_value=0, max_value=365),
)
def test_property_spoken_formatting_invariants(
    word: str, translation: str, pronunciation: str, days: int
) -> None:
    """Property test proving spoken formatting never exceeds length limit or crashes."""
    res_wod = format_word_of_day_spoken(
        word=word,
        language="spanish",
        translation=translation,
        pronunciation_hint=pronunciation,
        example_sentence="Ejemplo",
        example_translation="Example",
    )
    assert len(res_wod) <= MAX_SPOKEN_CHARS

    res_graded = format_graded_spoken(
        word=word,
        rating="good",
        interval_days=days,
        translation=translation,
    )
    assert len(res_graded) <= MAX_SPOKEN_CHARS
