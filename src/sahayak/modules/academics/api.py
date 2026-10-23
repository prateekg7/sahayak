"""Public API published by the academics module for cross-module interactions (T3.15).

Per AGENTS.md §7.1 and §1.2 Rule 6:
- Cross-module work goes through api.py or events.
- Never import across module boundaries.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, runtime_checkable

from sahayak.core.db.session import SessionFactory, UnitOfWork
from sahayak.modules.academics.adapters.progress import SQLAlchemyProgressRepository
from sahayak.modules.academics.domain.planner import resolve_current_date
from sahayak.modules.academics.domain.progress import (
    StreakInfo,
    TopicStatSummary,
    calculate_streak,
    calculate_weak_topics,
    calculate_weekly_summary,
    timestamps_to_dates,
)
from sahayak.modules.academics.ports import ProgressPort


@runtime_checkable
class AcademicsModuleAPI(Protocol):
    """Protocol for cross-module callers to interact with Academics capabilities."""

    async def get_streak(self, user_id: str | uuid.UUID, timezone_str: str = "UTC") -> int:
        """Return the current consecutive daily study streak count for a user."""
        ...

    async def get_streak_info(
        self, user_id: str | uuid.UUID, timezone_str: str = "UTC"
    ) -> StreakInfo:
        """Return full streak details (current streak, longest streak, active today)."""
        ...

    async def get_weak_topics(self, user_id: str | uuid.UUID, limit: int = 5) -> list[str]:
        """Return a list of the user's weakest topic display names ordered by lowest accuracy."""
        ...

    async def get_weekly_summary(
        self, user_id: str | uuid.UUID, timezone_str: str = "UTC"
    ) -> dict[str, Any]:
        """Return structured summary of the user's learning activity over the past 7 days."""
        ...

    async def get_due_flashcard_count(
        self, user_id: str | uuid.UUID, before: datetime | None = None
    ) -> int:
        """Return count of due flashcards for a user on or before the given timestamp."""
        ...

    async def get_today_study_tasks(
        self, user_id: str | uuid.UUID, timezone_str: str = "UTC"
    ) -> list[str]:
        """Return list of today's study plan task topics for user."""
        ...


class AcademicsAPI:
    """Implementation of AcademicsModuleAPI backed by SQLAlchemy and domain services."""

    def __init__(
        self,
        session_factory: SessionFactory,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    def _normalize_uuid(self, user_id: str | uuid.UUID) -> uuid.UUID:
        if isinstance(user_id, uuid.UUID):
            return user_id
        return uuid.UUID(str(user_id))

    async def get_streak(self, user_id: str | uuid.UUID, timezone_str: str = "UTC") -> int:
        """Return the current consecutive daily study streak count for a user."""
        info = await self.get_streak_info(user_id, timezone_str=timezone_str)
        return info.current_streak

    async def get_streak_info(
        self, user_id: str | uuid.UUID, timezone_str: str = "UTC"
    ) -> StreakInfo:
        """Return full streak details (current streak, longest streak, active today)."""
        uid = self._normalize_uuid(user_id)
        today = resolve_current_date(self._clock, user_timezone=timezone_str)

        async with UnitOfWork(self._session_factory) as uow:
            progress_repo: ProgressPort = SQLAlchemyProgressRepository(uow.session)
            timestamps = await progress_repo.get_activity_timestamps(uid)
            activity_dates = timestamps_to_dates(timestamps, user_timezone=timezone_str)
            return calculate_streak(activity_dates, today=today)

    async def get_weak_topics(self, user_id: str | uuid.UUID, limit: int = 5) -> list[str]:
        """Return a list of the user's weakest topic display names ordered by lowest accuracy."""
        uid = self._normalize_uuid(user_id)

        async with UnitOfWork(self._session_factory) as uow:
            progress_repo: ProgressPort = SQLAlchemyProgressRepository(uow.session)
            db_stats = await progress_repo.get_topic_stats(uid)
            topic_summaries: list[TopicStatSummary] = []
            for stat, display_name in db_stats:
                acc = round((stat.correct / stat.attempts) * 100.0, 1) if stat.attempts > 0 else 0.0
                topic_summaries.append(
                    TopicStatSummary(
                        topic=display_name,
                        attempts=stat.attempts,
                        correct=stat.correct,
                        accuracy_pct=acc,
                    )
                )

            weak_summaries = calculate_weak_topics(topic_summaries)
            return [w.topic for w in weak_summaries[:limit]]

    async def get_weekly_summary(
        self, user_id: str | uuid.UUID, timezone_str: str = "UTC"
    ) -> dict[str, Any]:
        """Return structured summary of the user's learning activity over the past 7 days."""
        uid = self._normalize_uuid(user_id)
        today = resolve_current_date(self._clock, user_timezone=timezone_str)
        now = self._clock()
        seven_days_ago = now - timedelta(days=7)

        async with UnitOfWork(self._session_factory) as uow:
            progress_repo: ProgressPort = SQLAlchemyProgressRepository(uow.session)
            timestamps = await progress_repo.get_activity_timestamps(uid)
            activity_dates = timestamps_to_dates(timestamps, user_timezone=timezone_str)

            (
                w_quizzes,
                w_questions,
                w_correct,
            ) = await progress_repo.get_quiz_performance_summary(uid, since=seven_days_ago)
            w_cards = await progress_repo.get_cards_reviewed_count(uid, since=seven_days_ago)

            summary = calculate_weekly_summary(
                activity_dates=activity_dates,
                today=today,
                quizzes_completed=w_quizzes,
                questions_answered=w_questions,
                correct_count=w_correct,
                cards_reviewed=w_cards,
            )

            return {
                "active_days": summary.active_days,
                "quizzes_completed": summary.quizzes_completed,
                "questions_answered": summary.questions_answered,
                "correct_count": summary.correct_count,
                "cards_reviewed": summary.cards_reviewed,
                "accuracy_pct": summary.accuracy_pct,
            }

    async def get_due_flashcard_count(
        self, user_id: str | uuid.UUID, before: datetime | None = None
    ) -> int:
        """Return count of due flashcards for a user on or before the given timestamp."""
        uid = self._normalize_uuid(user_id)
        now = before or self._clock()
        async with UnitOfWork(self._session_factory) as uow:
            from sahayak.modules.academics.adapters.flashcards import SQLAlchemyFlashcardRepository

            repo = SQLAlchemyFlashcardRepository(uow.session)
            return await repo.count_due_cards(uid, before=now)

    async def get_today_study_tasks(
        self, user_id: str | uuid.UUID, timezone_str: str = "UTC"
    ) -> list[str]:
        """Return list of today's study plan task topics for user."""
        uid = self._normalize_uuid(user_id)
        today = resolve_current_date(self._clock, user_timezone=timezone_str)
        async with UnitOfWork(self._session_factory) as uow:
            from sahayak.modules.academics.adapters.study_plans import (
                SQLAlchemyStudyPlanRepository,
            )

            repo = SQLAlchemyStudyPlanRepository(uow.session)
            active_plan = await repo.get_active_plan(uid, as_of=today)
            if active_plan is None:
                return []
            tasks = await repo.get_tasks_for_date(active_plan.id, target_date=today)
            return [t.topic for t in tasks if t.done_at is None]
