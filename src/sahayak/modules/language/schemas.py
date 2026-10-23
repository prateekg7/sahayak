"""Pydantic schemas for language module tools (T11.1)."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class VocabAction(StrEnum):
    """Supported actions for the vocab MCP tool."""

    WORD_OF_DAY = "word_of_day"
    REVIEW = "review"
    GRADE = "grade"
    STATS = "stats"
    ADD_WORD = "add_word"


class VocabRequest(BaseModel):
    """Input payload for the vocab tool."""

    action: VocabAction = Field(
        ...,
        description="Action to execute: word_of_day, review, grade, stats, or add_word.",
    )
    language: str | None = Field(
        None,
        description="Target language to practice (e.g. 'spanish', 'french', 'german', 'hindi').",
    )
    level: str | None = Field(
        None,
        description="Target level (beginner, intermediate, advanced).",
    )
    user_word_id: str | None = Field(
        None,
        description="ID of the user word record being graded in review.",
    )
    rating: str | None = Field(
        None,
        description="SuperMemo-2 feedback grade: 'again', 'hard', 'good', or 'easy'.",
    )
    word: str | None = Field(
        None,
        description="Word in target language for custom addition.",
    )
    translation: str | None = Field(
        None,
        description="English translation meaning.",
    )
    pronunciation_hint: str | None = Field(
        None,
        description="Phonetic text guide for spoken pronunciation.",
    )
    example_sentence: str | None = Field(
        None,
        description="Example sentence in target language.",
    )
    example_translation: str | None = Field(
        None,
        description="English translation of example sentence.",
    )


class WordData(BaseModel):
    """Vocabulary word details."""

    id: str
    language: str
    level: str
    word: str
    translation: str
    pronunciation_hint: str
    example_sentence: str
    example_translation: str
    part_of_speech: str | None = None


class UserWordData(BaseModel):
    """Learned word state with spaced repetition parameters."""

    id: str
    user_id: str
    word_id: str
    ease: float
    interval_days: int
    repetitions: int
    due_at: str
    last_reviewed_at: str | None = None
    word: WordData | None = None


class VocabResponseData(BaseModel):
    """Structured data returned in vocab MCP responses."""

    action: str
    language: str
    word: WordData | None = None
    user_word: UserWordData | None = None
    next_due_words: list[UserWordData] = Field(default_factory=list)
    stats: dict[str, Any] = Field(default_factory=dict)
