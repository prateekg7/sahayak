"""MCP tools for language learning module."""

from __future__ import annotations

from sahayak.modules.language.tools.language_practice import (
    LANGUAGE_PRACTICE_DESCRIPTION,
    get_language_practice_service,
    language_practice,
    set_language_practice_service,
)
from sahayak.modules.language.tools.vocab import (
    VOCAB_DESCRIPTION,
    get_vocab_service,
    set_vocab_service,
    vocab,
)

__all__ = [
    "LANGUAGE_PRACTICE_DESCRIPTION",
    "VOCAB_DESCRIPTION",
    "get_language_practice_service",
    "get_vocab_service",
    "language_practice",
    "set_language_practice_service",
    "set_vocab_service",
    "vocab",
]
