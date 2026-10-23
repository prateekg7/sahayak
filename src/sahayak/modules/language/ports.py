"""Abstract repository ports for the language module (T11.1)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Protocol

from sahayak.modules.language.models import UserWord, Word


class WordRepositoryPort(Protocol):
    """Port for language vocabulary words repository."""

    async def get_word_by_id(self, word_id: uuid.UUID) -> Word | None:
        """Retrieve word by primary key."""
        ...

    async def get_word_by_text(self, language: str, word: str) -> Word | None:
        """Retrieve word by language and word text."""
        ...

    async def create_word(self, word: Word) -> Word:
        """Persist a new word to the cache."""
        ...

    async def find_unlearned_words(
        self,
        user_id: uuid.UUID,
        language: str,
        level: str | None = None,
        limit: int = 10,
    ) -> list[Word]:
        """Find words in target language that user has not yet learned."""
        ...


class UserWordRepositoryPort(Protocol):
    """Port for user spaced repetition vocabulary repository."""

    async def get_user_word(self, user_id: uuid.UUID, word_id: uuid.UUID) -> UserWord | None:
        """Retrieve user's learning record for a specific word."""
        ...

    async def get_user_word_by_id(
        self,
        user_word_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> UserWord | None:
        """Retrieve user word record by its primary key with security check."""
        ...

    async def create_user_word(self, user_word: UserWord) -> UserWord:
        """Persist a new user word record."""
        ...

    async def save_user_word(self, user_word: UserWord) -> UserWord:
        """Update existing user word record."""
        ...

    async def get_due_words(
        self,
        user_id: uuid.UUID,
        language: str,
        now: datetime,
        limit: int = 10,
    ) -> list[UserWord]:
        """Retrieve words due for review (due_at <= now)."""
        ...

    async def get_words_learned_today(
        self,
        user_id: uuid.UUID,
        language: str,
        start_of_day: datetime,
    ) -> list[UserWord]:
        """Retrieve words added to user learning today."""
        ...

    async def get_stats(
        self,
        user_id: uuid.UUID,
        language: str,
        now: datetime,
    ) -> dict[str, int]:
        """Compute learning stats (total_learned, due_count, mastered_count)."""
        ...

    async def delete_all_for_user(self, user_id: uuid.UUID) -> int:
        """Delete all user words for GDPR right to be forgotten."""
        ...

    async def export_for_user(self, user_id: uuid.UUID) -> list[dict[str, Any]]:
        """Export all user learning records for GDPR right of access."""
        ...
