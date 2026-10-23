"""Domain models and formatters for local_info module (T12.1)."""

from __future__ import annotations

__all__ = [
    "MAX_SPOKEN_CHARS",
    "clean_spoken_text",
    "format_data_answer_spoken",
    "format_freshness_spoken",
    "format_relative_time_spoken",
    "format_spoken_attribution",
]

from sahayak.modules.local_info.domain.attribution import (
    MAX_SPOKEN_CHARS,
    clean_spoken_text,
    format_data_answer_spoken,
    format_freshness_spoken,
    format_relative_time_spoken,
    format_spoken_attribution,
)
