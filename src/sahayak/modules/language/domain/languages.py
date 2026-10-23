"""Language and proficiency level constants and normalization."""

from __future__ import annotations

from sahayak.core.errors import InvalidInputError

SUPPORTED_LANGUAGES: tuple[str, ...] = (
    "spanish",
    "french",
    "german",
    "hindi",
    "japanese",
    "italian",
    "mandarin",
)

SUPPORTED_LEVELS: tuple[str, ...] = (
    "beginner",
    "intermediate",
    "advanced",
)

DEFAULT_LANGUAGE: str = "spanish"
DEFAULT_LEVEL: str = "beginner"


def normalize_language(raw_lang: str | None) -> str:
    """Normalize and validate target language.

    Args:
        raw_lang: Input language string (e.g. 'Spanish', ' es ', None).

    Returns:
        Canonical lowercase language string.

    Raises:
        InvalidInputError: If language is unsupported.
    """
    if not raw_lang:
        return DEFAULT_LANGUAGE

    clean = raw_lang.strip().lower()

    # Common aliases
    aliases: dict[str, str] = {
        "es": "spanish",
        "esp": "spanish",
        "espanol": "spanish",
        "español": "spanish",
        "fr": "french",
        "francais": "french",
        "français": "french",
        "de": "german",
        "deutsch": "german",
        "hi": "hindi",
        "ja": "japanese",
        "jp": "japanese",
        "nihongo": "japanese",
        "it": "italian",
        "italiano": "italian",
        "zh": "mandarin",
        "chinese": "mandarin",
    }

    resolved = aliases.get(clean, clean)
    if resolved not in SUPPORTED_LANGUAGES:
        supported_str = ", ".join(SUPPORTED_LANGUAGES)
        raise InvalidInputError(
            f"Unsupported language '{raw_lang}'. Supported languages are: {supported_str}."
        )

    return resolved


def normalize_level(raw_level: str | None) -> str:
    """Normalize and validate proficiency level.

    Args:
        raw_level: Input level string (e.g. 'A1', 'beginner', None).

    Returns:
        Canonical level string ('beginner', 'intermediate', 'advanced').

    Raises:
        InvalidInputError: If level is unrecognized.
    """
    if not raw_level:
        return DEFAULT_LEVEL

    clean = raw_level.strip().lower()

    level_aliases: dict[str, str] = {
        "a1": "beginner",
        "a2": "beginner",
        "basic": "beginner",
        "easy": "beginner",
        "b1": "intermediate",
        "b2": "intermediate",
        "medium": "intermediate",
        "c1": "advanced",
        "c2": "advanced",
        "hard": "advanced",
    }

    resolved = level_aliases.get(clean, clean)
    if resolved not in SUPPORTED_LEVELS:
        levels_str = ", ".join(SUPPORTED_LEVELS)
        raise InvalidInputError(
            f"Unsupported proficiency level '{raw_level}'. Supported levels are: {levels_str}."
        )

    return resolved
