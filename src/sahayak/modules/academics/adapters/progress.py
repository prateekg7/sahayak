"""SQLAlchemy repository implementation for progress tracking and activity logs (T3.13)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sahayak.modules.academics.models import ActivityLog, Quiz, QuizStatus, Topic, TopicStats
from sahayak.modules.academics.ports import ProgressPort


class SQLAlchemyProgressRepository(ProgressPort):
    """PostgreSQL adapter managing activity logs and topic performance counters."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record_activity(
        self,
        user_id: uuid.UUID,
        activity_type: str,
        event_id: uuid.UUID,
        created_at: datetime,
        meta: dict[str, Any] | None = None,
    ) -> bool:
        """Record an activity event idempotently."""
        # 1. Check if event_id has already been processed
        stmt = select(ActivityLog.id).where(ActivityLog.event_id == event_id)
        res = await self._session.execute(stmt)
        if res.scalar_one_or_none() is not None:
            return False

        # 2. Insert new activity log record
        log = ActivityLog(
            id=uuid.uuid4(),
            user_id=user_id,
            activity_type=activity_type,
            event_id=event_id,
            created_at=created_at,
            meta=meta,
        )
        self._session.add(log)
        await self._session.flush()
        return True

    async def update_topic_stats(
        self,
        user_id: uuid.UUID,
        topic_id: uuid.UUID,
        attempts_delta: int,
        correct_delta: int,
        timestamp: datetime,
    ) -> TopicStats:
        """Atomically upsert topic statistics."""
        stmt = (
            select(TopicStats)
            .where(TopicStats.user_id == user_id, TopicStats.topic_id == topic_id)
            .with_for_update()
        )
        res = await self._session.execute(stmt)
        stats = res.scalar_one_or_none()

        if stats is not None:
            stats.attempts += attempts_delta
            stats.correct += correct_delta
            if timestamp > stats.last_attempt_at:
                stats.last_attempt_at = timestamp
        else:
            stats = TopicStats(
                user_id=user_id,
                topic_id=topic_id,
                attempts=attempts_delta,
                correct=correct_delta,
                last_attempt_at=timestamp,
            )
            self._session.add(stats)

        await self._session.flush()
        return stats

    async def get_topic_stats(
        self,
        user_id: uuid.UUID,
    ) -> Sequence[tuple[TopicStats, str]]:
        """Fetch all topic stats for a user paired with topic display names."""
        stmt = (
            select(TopicStats, Topic.display_name)
            .join(Topic, Topic.id == TopicStats.topic_id)
            .where(TopicStats.user_id == user_id)
            .order_by(TopicStats.attempts.desc())
        )
        res = await self._session.execute(stmt)
        return list(res.all())

    async def get_activity_timestamps(
        self,
        user_id: uuid.UUID,
        since: datetime | None = None,
    ) -> Sequence[datetime]:
        """Fetch all study activity timestamps for a user."""
        stmt1 = select(ActivityLog.created_at).where(ActivityLog.user_id == user_id)
        if since is not None:
            stmt1 = stmt1.where(ActivityLog.created_at >= since)
        res1 = await self._session.execute(stmt1)
        timestamps = list(res1.scalars().all())

        stmt2 = select(Quiz.finished_at).where(
            Quiz.user_id == user_id,
            Quiz.finished_at.is_not(None),
        )
        if since is not None:
            stmt2 = stmt2.where(Quiz.finished_at >= since)
        res2 = await self._session.execute(stmt2)
        for ts in res2.scalars().all():
            if ts is not None:
                timestamps.append(ts)

        return timestamps

    async def get_quiz_performance_summary(
        self,
        user_id: uuid.UUID,
        since: datetime | None = None,
    ) -> tuple[int, int, int]:
        """Return (completed_quizzes_count, total_questions, correct_questions)."""
        stmt = select(
            func.count(Quiz.id),
            func.coalesce(func.sum(Quiz.total), 0),
            func.coalesce(func.sum(Quiz.score_correct), 0),
        ).where(Quiz.user_id == user_id, Quiz.status == QuizStatus.COMPLETED)
        if since is not None:
            stmt = stmt.where(Quiz.finished_at >= since)

        res = await self._session.execute(stmt)
        row = res.one()
        return (int(row[0]), int(row[1]), int(row[2]))

    async def get_cards_reviewed_count(
        self,
        user_id: uuid.UUID,
        since: datetime | None = None,
    ) -> int:
        """Count flashcard reviews recorded for a user."""
        stmt = select(func.count(ActivityLog.id)).where(
            ActivityLog.user_id == user_id,
            ActivityLog.activity_type == "flashcard",
        )
        if since is not None:
            stmt = stmt.where(ActivityLog.created_at >= since)

        res = await self._session.execute(stmt)
        return int(res.scalar_one())
