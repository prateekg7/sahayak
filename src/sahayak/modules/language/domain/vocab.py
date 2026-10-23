"""Domain formatting and validation for vocabulary and spaced repetition (T11.1)."""

from __future__ import annotations

import re

from sahayak.core.errors import InvalidInputError

MAX_SPOKEN_CHARS: int = 300


def sanitize_spoken_text(text: str) -> str:
    """Remove markdown formatting, quotes, and forbidden symbols for clean speech.

    Args:
        text: Raw text string.

    Returns:
        Clean, voice-friendly text string.
    """
    clean = re.sub(r"[*_#`~]", "", text)
    clean = clean.replace('"', "").replace("'", "")
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def format_word_of_day_spoken(
    word: str,
    language: str,
    translation: str,
    pronunciation_hint: str,
    example_sentence: str,
    example_translation: str,
    is_already_learned: bool = False,
) -> str:
    """Format voice spoken summary for word of the day."""
    lang_display = language.capitalize()
    prefix = (
        f"Your word of the day in {lang_display} is {word}, meaning {translation}. "
        if not is_already_learned
        else f"Your word today in {lang_display} is {word}, meaning {translation}. "
    )
    pronounce_part = f"Pronounced {pronunciation_hint}. "
    example_part = f"Example: {example_sentence}, meaning {example_translation}. "
    action_part = "Say review or ask for another word."

    full = f"{prefix}{pronounce_part}{example_part}{action_part}"
    clean = sanitize_spoken_text(full)
    if len(clean) > MAX_SPOKEN_CHARS:
        # Truncate example translation if necessary to respect length limit
        truncated = f"{prefix}{pronounce_part}Example: {example_sentence}. {action_part}"
        clean = sanitize_spoken_text(truncated)
        if len(clean) > MAX_SPOKEN_CHARS:
            clean = sanitize_spoken_text(f"{prefix}{pronounce_part}{action_part}")

    return clean[:MAX_SPOKEN_CHARS]


def format_review_card_spoken(
    word: str,
    language: str,
    pronunciation_hint: str,
    remaining_count: int,
) -> str:
    """Format voice review prompt for a spaced repetition card."""
    lang_display = language.capitalize()
    remaining_text = (
        " One more word due."
        if remaining_count == 1
        else f" {remaining_count} words due."
        if remaining_count > 1
        else ""
    )

    prompt = (
        f"How do you translate {word} in {lang_display}? "
        f"Pronounced {pronunciation_hint}. "
        f"Say your answer or grade easy, good, or hard.{remaining_text}"
    )
    clean = sanitize_spoken_text(prompt)
    return clean[:MAX_SPOKEN_CHARS]


def format_graded_spoken(
    word: str,
    rating: str,
    interval_days: int,
    translation: str | None = None,
) -> str:
    """Format voice confirmation after grading a spaced repetition review."""
    meaning_text = f" which means {translation}" if translation else ""
    if interval_days == 1:
        interval_text = "tomorrow"
    elif interval_days == 0:
        interval_text = "later today"
    else:
        interval_text = f"in {interval_days} days"

    text = f"Marked {word}{meaning_text} as {rating}. Scheduled for review {interval_text}."
    clean = sanitize_spoken_text(text)
    if len(clean) > MAX_SPOKEN_CHARS:
        clean = sanitize_spoken_text(
            f"Marked {word} as {rating}. Scheduled for review {interval_text}."
        )
    return clean[:MAX_SPOKEN_CHARS]


def format_stats_spoken(
    language: str,
    total_learned: int,
    due_count: int,
    mastered_count: int,
) -> str:
    """Format voice summary of vocabulary statistics."""
    lang_display = language.capitalize()
    words_str = "word" if total_learned == 1 else "words"
    due_str = (
        "no words due for review"
        if due_count == 0
        else "one word due for review"
        if due_count == 1
        else f"{due_count} words due for review"
    )

    msg = (
        f"In {lang_display}, you have learned {total_learned} {words_str} "
        f"with {mastered_count} mastered, and {due_str} today."
    )
    clean = sanitize_spoken_text(msg)
    return clean[:MAX_SPOKEN_CHARS]


def validate_word_payload(
    word: str,
    translation: str,
    pronunciation_hint: str,
) -> None:
    """Validate word creation payload fields."""
    if not word or not word.strip():
        raise InvalidInputError("Word must not be empty.")
    if len(word) > 100:
        raise InvalidInputError("Word exceeds 100 characters limit.")
    if not translation or not translation.strip():
        raise InvalidInputError("Translation must not be empty.")
    if len(translation) > 255:
        raise InvalidInputError("Translation exceeds 255 characters limit.")
    if not pronunciation_hint or not pronunciation_hint.strip():
        raise InvalidInputError("Pronunciation hint must not be empty.")
    if len(pronunciation_hint) > 255:
        raise InvalidInputError("Pronunciation hint exceeds 255 characters limit.")
