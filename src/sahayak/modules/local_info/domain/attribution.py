"""Domain logic for external data freshness and speech attribution (T12.1)."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from sahayak.modules.local_info.ports import DataSourceResult

MAX_SPOKEN_CHARS = 300


def clean_spoken_text(text: str) -> str:
    """Strip markdown, asterisks, brackets, and emojis for natural voice synthesis."""
    cleaned = re.sub(r"[*_`#~\[\]\(\)\{\}\<\>\"\'\\\/]", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"\s+([:!?,.])", r"\1", cleaned)
    return cleaned


def format_relative_time_spoken(dt: datetime, now: datetime) -> str:
    """Format timestamp into a short, natural speech relative time."""
    diff_seconds = max(0, int((now - dt).total_seconds()))

    if diff_seconds < 120:
        return "just now"
    if diff_seconds < 3600:
        minutes = diff_seconds // 60
        return f"about {minutes} minutes ago"
    if diff_seconds < 86400:
        hours = diff_seconds // 3600
        unit = "hour" if hours == 1 else "hours"
        return f"about {hours} {unit} ago"

    days = diff_seconds // 86400
    unit = "day" if days == 1 else "days"
    return f"about {days} {unit} ago"


def format_freshness_spoken(
    result: DataSourceResult[Any],
    now: datetime,
) -> str:
    """Format voice freshness prefix indicating data age or cached stale state."""
    ref_time = result.cached_at if result.is_stale and result.cached_at else result.fetched_at
    rel_time = format_relative_time_spoken(ref_time, now)

    if result.is_stale:
        return f"Using cached update from {rel_time}."
    return f"As of {rel_time}."


def format_spoken_attribution(
    source_name: str,
    attribution: str,
) -> str:
    """Format clean voice attribution phrase."""
    clean_name = clean_spoken_text(source_name)
    return f"According to {clean_name}"


def format_data_answer_spoken(
    prefix: str,
    body: str,
    freshness: str | None = None,
    source_name: str | None = None,
) -> str:
    """Assemble a complete spoken summary adhering strictly to length limits."""
    parts: list[str] = []
    if source_name:
        parts.append(format_spoken_attribution(source_name, ""))
    if freshness:
        parts.append(freshness)
    if prefix:
        parts.append(prefix)
    parts.append(body)

    joined = ". ".join(p.rstrip(". ") for p in parts if p.strip()) + "."
    cleaned = clean_spoken_text(joined)
    if len(cleaned) > MAX_SPOKEN_CHARS:
        # Fallback to body + freshness or body alone to guarantee voice length
        compact = f"{body.rstrip('. ')}."
        if freshness:
            compact = f"{freshness.rstrip('. ')}. {compact}"
        cleaned = clean_spoken_text(compact)
        if len(cleaned) > MAX_SPOKEN_CHARS:
            cleaned = clean_spoken_text(body)[:MAX_SPOKEN_CHARS]
    return cleaned[:MAX_SPOKEN_CHARS]
