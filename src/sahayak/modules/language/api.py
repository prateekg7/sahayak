"""Public API for cross-module interactions with the language module."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sahayak.core.db.session import UnitOfWork
from sahayak.modules.language.adapters.vocab import SQLAlchemyUserWordRepository
from sahayak.modules.language.domain.languages import normalize_language


class LanguageModuleAPI(Protocol):
    """Protocol defining the public interface exposed by the language module."""

    async def get_due_vocab_count(
        self,
        user_id: uuid.UUID,
        language: str | None = None,
    ) -> int:
        """Return the number of vocabulary words due for review."""
        ...


class LanguageAPI:
    """Implementation of LanguageModuleAPI."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    async def get_due_vocab_count(
        self,
        user_id: uuid.UUID,
        language: str | None = None,
    ) -> int:
        lang = normalize_language(language)
        now = self._clock()
        async with UnitOfWork(self._session_factory) as uow:
            repo = SQLAlchemyUserWordRepository(uow.session)
            stats = await repo.get_stats(user_id=user_id, language=lang, now=now)
            return stats["due_count"]
