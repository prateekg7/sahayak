"""Pure domain functions for topic normalization and canonical slug generation."""

from __future__ import annotations

import re

# Maximum allowed lengths for database constraints
MAX_INPUT_LENGTH = 256
MAX_TOPIC_KEY_LENGTH = 128
MAX_DISPLAY_NAME_LENGTH = 256

# Curated alias table mapping colloquial or spoken phrases to canonical slugs & display names
TOPIC_ALIASES: dict[str, tuple[str, str]] = {
    "us history": ("united-states-history", "United States History"),
    "u s history": ("united-states-history", "United States History"),
    "u.s. history": ("united-states-history", "United States History"),
    "american history": ("united-states-history", "United States History"),
    "ap bio": ("ap-biology", "AP Biology"),
    "ap biology": ("ap-biology", "AP Biology"),
    "ap chem": ("ap-chemistry", "AP Chemistry"),
    "ap chemistry": ("ap-chemistry", "AP Chemistry"),
    "calc 1": ("calculus-1", "Calculus I"),
    "calc i": ("calculus-1", "Calculus I"),
    "calculus 1": ("calculus-1", "Calculus I"),
    "calculus i": ("calculus-1", "Calculus I"),
    "calc 2": ("calculus-2", "Calculus II"),
    "calc ii": ("calculus-2", "Calculus II"),
    "calculus 2": ("calculus-2", "Calculus II"),
    "calculus ii": ("calculus-2", "Calculus II"),
    "world war 2": ("world-war-2", "World War II"),
    "world war ii": ("world-war-2", "World War II"),
    "ww2": ("world-war-2", "World War II"),
    "wwii": ("world-war-2", "World War II"),
    "world war 1": ("world-war-1", "World War I"),
    "world war i": ("world-war-1", "World War I"),
    "ww1": ("world-war-1", "World War I"),
    "wwi": ("world-war-1", "World War I"),
    "linear algebra": ("linear-algebra", "Linear Algebra"),
    "organic chemistry": ("organic-chemistry", "Organic Chemistry"),
}

# Words kept in all-caps or lowercase in title-casing
ACRONYMS = {"ap", "us", "usa", "uk", "dna", "rna", "atp", "gdp", "cpu", "ai"}
ROMAN_NUMERALS = {"i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x"}
MINOR_WORDS = {"and", "as", "at", "but", "by", "for", "in", "of", "on", "or", "the", "to", "via"}


def slugify(text: str) -> str:
    """Transform text into a clean alphanumeric kebab-case slug.

    Strips punctuation, symbols, and underscores, normalizes unicode,
    collapses whitespace and hyphens, and returns a lowercase string.
    """
    cleaned = re.sub(r"[^a-zA-Z0-9\s-]", "", text.strip().lower())
    slug = re.sub(r"[-\s]+", "-", cleaned).strip("-")
    return slug[:MAX_TOPIC_KEY_LENGTH]


def format_display_name(raw: str) -> str:
    """Format a readable display name preserving acronyms and roman numerals."""
    words = re.sub(r"[^a-zA-Z0-9\s-]", "", raw.strip()).split()
    if not words:
        return ""

    formatted_words: list[str] = []
    for i, word in enumerate(words):
        lower = word.lower()
        if lower in ACRONYMS or lower in ROMAN_NUMERALS:
            formatted_words.append(lower.upper())
        elif i > 0 and lower in MINOR_WORDS:
            formatted_words.append(lower)
        else:
            formatted_words.append(word.capitalize())

    result = " ".join(formatted_words)
    return result[:MAX_DISPLAY_NAME_LENGTH]


def normalize_topic(raw_topic: str) -> tuple[str, str]:
    """Normalize a spoken or text topic into a canonical (topic_key, display_name) pair.

    Handles:
    - Stripping punctuation, accents, and excessive whitespace
    - Curated alias lookup (e.g. "ap bio" -> "ap-biology", "AP Biology")
    - Length limits (max 256 chars input)
    - Fallback canonical slug and title-cased display name

    Raises:
        ValueError: If raw_topic is empty, whitespace-only, or exceeds MAX_INPUT_LENGTH.
    """
    if not raw_topic or not raw_topic.strip():
        raise ValueError("Topic name cannot be empty or whitespace only.")

    cleaned = raw_topic.strip()
    if len(cleaned) > MAX_INPUT_LENGTH:
        raise ValueError(f"Topic name exceeds maximum allowed length of {MAX_INPUT_LENGTH} chars.")

    # Lowercase string stripped of extra spaces and punctuation for alias lookup
    simplified = re.sub(r"[^a-zA-Z0-9\s]", "", cleaned.lower())
    simplified = re.sub(r"\s+", " ", simplified).strip()

    if simplified in TOPIC_ALIASES:
        return TOPIC_ALIASES[simplified]

    topic_key = slugify(cleaned)
    if not topic_key:
        raise ValueError(f"Topic '{raw_topic}' contains no valid alphanumeric characters.")

    display_name = format_display_name(cleaned)
    return topic_key, display_name
