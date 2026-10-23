"""SQLAlchemy repository implementations for vocabulary learning (T11.1)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from sahayak.modules.language.models import UserWord, Word
from sahayak.modules.language.ports import UserWordRepositoryPort, WordRepositoryPort


class SQLAlchemyWordRepository(WordRepositoryPort):
    """SQLAlchemy implementation of WordRepositoryPort."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_word_by_id(self, word_id: uuid.UUID) -> Word | None:
        stmt = select(Word).where(Word.id == word_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_word_by_text(self, language: str, word: str) -> Word | None:
        stmt = select(Word).where(
            Word.language == language.lower(),
            func.lower(Word.word) == word.lower().strip(),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_word(self, word: Word) -> Word:
        self._session.add(word)
        await self._session.flush()
        return word

    async def find_unlearned_words(
        self,
        user_id: uuid.UUID,
        language: str,
        level: str | None = None,
        limit: int = 10,
    ) -> list[Word]:
        learned_subquery = select(UserWord.word_id).where(UserWord.user_id == user_id)
        stmt = select(Word).where(
            Word.language == language.lower(),
            Word.id.not_in(learned_subquery),
        )
        if level:
            stmt = stmt.where(Word.level == level.lower())

        stmt = stmt.order_by(Word.created_at.asc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class SQLAlchemyUserWordRepository(UserWordRepositoryPort):
    """SQLAlchemy implementation of UserWordRepositoryPort."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_user_word(self, user_id: uuid.UUID, word_id: uuid.UUID) -> UserWord | None:
        stmt = (
            select(UserWord)
            .options(selectinload(UserWord.word))
            .where(UserWord.user_id == user_id, UserWord.word_id == word_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_user_word_by_id(
        self,
        user_word_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> UserWord | None:
        stmt = (
            select(UserWord)
            .options(selectinload(UserWord.word))
            .where(UserWord.id == user_word_id, UserWord.user_id == user_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_user_word(self, user_word: UserWord) -> UserWord:
        self._session.add(user_word)
        await self._session.flush()
        return user_word

    async def save_user_word(self, user_word: UserWord) -> UserWord:
        self._session.add(user_word)
        await self._session.flush()
        return user_word

    async def get_due_words(
        self,
        user_id: uuid.UUID,
        language: str,
        now: datetime,
        limit: int = 10,
    ) -> list[UserWord]:
        stmt = (
            select(UserWord)
            .join(Word, UserWord.word_id == Word.id)
            .options(selectinload(UserWord.word))
            .where(
                UserWord.user_id == user_id,
                Word.language == language.lower(),
                UserWord.due_at <= now,
            )
            .order_by(UserWord.due_at.asc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_words_learned_today(
        self,
        user_id: uuid.UUID,
        language: str,
        start_of_day: datetime,
    ) -> list[UserWord]:
        stmt = (
            select(UserWord)
            .join(Word, UserWord.word_id == Word.id)
            .options(selectinload(UserWord.word))
            .where(
                UserWord.user_id == user_id,
                Word.language == language.lower(),
                UserWord.created_at >= start_of_day,
            )
            .order_by(UserWord.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_stats(
        self,
        user_id: uuid.UUID,
        language: str,
        now: datetime,
    ) -> dict[str, int]:
        base_query = (
            select(UserWord)
            .join(Word, UserWord.word_id == Word.id)
            .where(UserWord.user_id == user_id, Word.language == language.lower())
        )
        total_result = await self._session.execute(
            select(func.count()).select_from(base_query.subquery())
        )
        total_learned = total_result.scalar_one() or 0

        due_query = base_query.where(UserWord.due_at <= now)
        due_result = await self._session.execute(
            select(func.count()).select_from(due_query.subquery())
        )
        due_count = due_result.scalar_one() or 0

        mastered_query = base_query.where(UserWord.repetitions >= 3)
        mastered_result = await self._session.execute(
            select(func.count()).select_from(mastered_query.subquery())
        )
        mastered_count = mastered_result.scalar_one() or 0

        return {
            "total_learned": total_learned,
            "due_count": due_count,
            "mastered_count": mastered_count,
        }

    async def delete_all_for_user(self, user_id: uuid.UUID) -> int:
        stmt = delete(UserWord).where(UserWord.user_id == user_id)
        result = await self._session.execute(stmt)
        rowcount = getattr(result, "rowcount", 0)
        return int(rowcount) if isinstance(rowcount, int) else 0

    async def export_for_user(self, user_id: uuid.UUID) -> list[dict[str, Any]]:
        stmt = (
            select(UserWord)
            .options(selectinload(UserWord.word))
            .where(UserWord.user_id == user_id)
            .order_by(UserWord.created_at.asc())
        )
        result = await self._session.execute(stmt)
        return [uw.to_dict() for uw in result.scalars().all()]
