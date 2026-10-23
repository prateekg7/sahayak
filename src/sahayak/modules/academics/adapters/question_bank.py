"""SQLAlchemy implementation of QuestionBankPort."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from sahayak.modules.academics.models import (
    DifficultyLevel,
    Question,
    QuestionStatus,
    Topic,
)
from sahayak.modules.academics.ports import DEFAULT_QUARANTINE_THRESHOLD, QuestionBankPort


class SQLAlchemyQuestionBank(QuestionBankPort):
    """PostgreSQL question-bank repository handling topics, questions, and deduplication."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create_topic(self, topic_key: str, display_name: str) -> Topic:
        """Find an existing topic by canonical key or insert a new one."""
        stmt = select(Topic).where(Topic.topic_key == topic_key)
        res = await self._session.execute(stmt)
        topic = res.scalar_one_or_none()
        if topic is not None:
            return topic

        topic = Topic(topic_key=topic_key, display_name=display_name)
        self._session.add(topic)
        try:
            await self._session.flush()
            return topic
        except IntegrityError:
            # Handle race condition from concurrent insert
            res = await self._session.execute(stmt)
            return res.scalar_one()

    async def find_topic(self, topic_key: str) -> Topic | None:
        """Find a topic by canonical key if it exists."""
        stmt = select(Topic).where(Topic.topic_key == topic_key)
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def find_questions(
        self,
        topic_key: str,
        difficulty: DifficultyLevel,
        exclude_ids: Sequence[uuid.UUID] | None = None,
        status: QuestionStatus = QuestionStatus.APPROVED,
        limit: int = 5,
    ) -> Sequence[Question]:
        """Fetch available questions for a topic matching difficulty and status.

        Joins Topic in a single query to eliminate N+1 overhead.
        """
        stmt = (
            select(Question)
            .join(Topic, Question.topic_id == Topic.id)
            .where(
                Topic.topic_key == topic_key,
                Question.difficulty == difficulty,
                Question.status == status,
            )
        )
        if exclude_ids:
            stmt = stmt.where(Question.id.not_in(exclude_ids))

        stmt = stmt.limit(limit)
        res = await self._session.execute(stmt)
        return list(res.scalars().all())

    async def insert_questions(self, questions: Sequence[Question]) -> Sequence[Question]:
        """Persist questions into the bank with deduplication by content_hash."""
        if not questions:
            return []

        hashes = [q.content_hash for q in questions]
        existing_stmt = select(Question).where(Question.content_hash.in_(hashes))
        existing_res = await self._session.execute(existing_stmt)
        existing = list(existing_res.scalars().all())
        existing_hashes = {q.content_hash for q in existing}

        to_insert = [q for q in questions if q.content_hash not in existing_hashes]
        if to_insert:
            self._session.add_all(to_insert)
            try:
                await self._session.flush()
            except IntegrityError:
                # Concurrent insert race condition: reload existing from DB
                reloaded = await self._session.execute(existing_stmt)
                return list(reloaded.scalars().all())

        return existing + to_insert

    async def count_available(
        self,
        topic_key: str,
        difficulty: DifficultyLevel,
        exclude_ids: Sequence[uuid.UUID] | None = None,
        status: QuestionStatus = QuestionStatus.APPROVED,
    ) -> int:
        """Count remaining available questions matching criteria."""
        stmt = (
            select(func.count(Question.id))
            .join(Topic, Question.topic_id == Topic.id)
            .where(
                Topic.topic_key == topic_key,
                Question.difficulty == difficulty,
                Question.status == status,
            )
        )
        if exclude_ids:
            stmt = stmt.where(Question.id.not_in(exclude_ids))

        res = await self._session.execute(stmt)
        count = res.scalar_one()
        return int(count or 0)

    async def flag_question(
        self,
        question_id: uuid.UUID,
        quarantine_threshold: int = DEFAULT_QUARANTINE_THRESHOLD,
    ) -> Question | None:
        """Increment flag_count on a question and quarantine if threshold is reached."""
        stmt = select(Question).where(Question.id == question_id)
        res = await self._session.execute(stmt)
        question = res.scalar_one_or_none()
        if question is None:
            return None

        question.flag_count += 1
        if question.flag_count >= quarantine_threshold:
            question.status = QuestionStatus.QUARANTINED
        else:
            question.status = QuestionStatus.FLAGGED

        await self._session.flush()
        return question

    async def quarantine_question(self, question_id: uuid.UUID) -> Question | None:
        """Directly transition a question to quarantined status."""
        stmt = select(Question).where(Question.id == question_id)
        res = await self._session.execute(stmt)
        question = res.scalar_one_or_none()
        if question is None:
            return None

        question.status = QuestionStatus.QUARANTINED
        await self._session.flush()
        return question
