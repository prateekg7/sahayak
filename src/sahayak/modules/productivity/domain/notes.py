"""Domain models, speech truncation, and chunking for voice notes (T5.3)."""

from __future__ import annotations

from typing import Any

from sahayak.core.errors import InvalidInputError

MAX_NOTE_LENGTH = 2000
DEFAULT_CHUNK_CHARS = 240


def clean_note_text(text: str) -> str:
    """Validate and normalize note content."""
    if not text or not text.strip():
        raise InvalidInputError("Note content cannot be empty")
    clean = text.strip()
    if len(clean) > MAX_NOTE_LENGTH:
        raise InvalidInputError(
            f"Note exceeds maximum length of {MAX_NOTE_LENGTH} characters (got {len(clean)})"
        )
    return clean


def chunk_note_for_speech(content: str, max_chars: int = DEFAULT_CHUNK_CHARS) -> tuple[str, bool]:
    """Chunk note text for voice speech.

    If content exceeds max_chars, breaks cleanly on word or sentence boundary
    and appends a voice prompt.

    Returns:
        tuple[str, bool]: (spoken_text, has_more).
    """
    clean = content.strip()
    if len(clean) <= max_chars:
        return clean, False

    cutoff = max_chars - 35
    boundary = clean.rfind(". ", 0, cutoff)
    if boundary == -1:
        boundary = clean.rfind(" ", 0, cutoff)
    if boundary == -1:
        boundary = cutoff

    chunk = clean[:boundary].strip()
    spoken = f"{chunk}... Ask me to read more to continue."
    return spoken, True


def format_search_results_spoken(query: str, notes: list[dict[str, Any]]) -> str:
    """Format search results for speech under 300 characters."""
    if not notes:
        return f"I could not find any notes matching {query}."

    count = len(notes)
    if count == 1:
        content_preview, _ = chunk_note_for_speech(notes[0].get("content", ""), 200)
        return f"Found 1 note for {query}: {content_preview}"

    previews: list[str] = []
    for i, n in enumerate(notes[:2]):
        snippet, _ = chunk_note_for_speech(n.get("content", ""), 100)
        previews.append(f"Note {i + 1}: {snippet}")

    summary = f"Found {count} notes matching {query}. {'. '.join(previews)}."
    if count > 2:
        summary += f" And {count - 2} more."

    if len(summary) > 300:
        summary = summary[:296] + "..."
    return summary
