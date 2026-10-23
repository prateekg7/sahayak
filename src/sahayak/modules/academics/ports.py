"""Ports and interface definitions for Academics module repositories and external adapters."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Protocol

from sahayak.modules.academics.models import (
    DifficultyLevel,
    Question,
    QuestionStatus,
    Topic,
)

# Threshold of user flags before a question is automatically quarantined from serving
DEFAULT_QUARANTINE_THRESHOLD = 3


class QuestionBankPort(Protocol):
    """Repository port for academic topics and multiple-choice questions."""

    async def get_or_create_topic(self, topic_key: str, display_name: str) -> Topic:
        """Find an existing topic by canonical key or insert a new one."""
        ...

    async def find_topic(self, topic_key: str) -> Topic | None:
        """Find a topic by canonical key if it exists."""
        ...

    async def find_questions(
        self,
        topic_key: str,
        difficulty: DifficultyLevel,
        exclude_ids: Sequence[uuid.UUID] | None = None,
        status: QuestionStatus = QuestionStatus.APPROVED,
        limit: int = 5,
    ) -> Sequence[Question]:
        """Fetch available questions for a topic matching difficulty and status.

        Excludes question IDs already served or seen.
        """
        ...

    async def insert_questions(self, questions: Sequence[Question]) -> Sequence[Question]:
        """Persist questions into the bank with deduplication by content_hash.

        Returns the sequence of persisted questions.
        """
        ...

    async def count_available(
        self,
        topic_key: str,
        difficulty: DifficultyLevel,
        exclude_ids: Sequence[uuid.UUID] | None = None,
        status: QuestionStatus = QuestionStatus.APPROVED,
    ) -> int:
        """Count remaining available questions matching criteria."""
        ...

    async def flag_question(
        self,
        question_id: uuid.UUID,
        quarantine_threshold: int = DEFAULT_QUARANTINE_THRESHOLD,
    ) -> Question | None:
        """Increment flag_count on a question and quarantine if threshold is reached."""
        ...

    async def quarantine_question(self, question_id: uuid.UUID) -> Question | None:
        """Directly transition a question to quarantined status."""
        ...
