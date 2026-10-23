"""Service layer orchestrating study progress, streaks, and weak-topic analytics (T3.13)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sahayak.core.db.session import SessionFactory, UnitOfWork
from sahayak.core.events import DomainEvent
from sahayak.modules.academics.adapters.progress import SQLAlchemyProgressRepository
from sahayak.modules.academics.adapters.question_bank import SQLAlchemyQuestionBank
from sahayak.modules.academics.domain.planner import resolve_current_date
from sahayak.modules.academics.domain.progress import (
    StreakInfo,
    TopicStatSummary,
    calculate_streak,
    calculate_weak_topics,
    calculate_weekly_summary,
    format_streak_spoken,
    format_summary_spoken,
    format_weak_topics_spoken,
    format_weekly_spoken,
    timestamps_to_dates,
)
from sahayak.modules.academics.domain.topics import normalize_topic
from sahayak.modules.academics.models import Deck
from sahayak.modules.academics.ports import ProgressPort, QuestionBankPort
from sahayak.modules.academics.schemas import (
    ProgressReportResponseData,
    ProgressScope,
    StreakData,
    WeakTopicData,
    WeeklySummaryData,
)

Clock = Callable[[], datetime]


class ProgressService:
    """Domain service managing user study progress, streak tracking, and event subscriptions."""

    def __init__(
        self,
        session_factory: SessionFactory,
        clock: Clock | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._clock: Clock = clock or (lambda: datetime.now(UTC))

    # ---------------------------------------------------------------------------
    # Event Handlers (Idempotent)
    # ---------------------------------------------------------------------------

    async def handle_quiz_finished(self, event: DomainEvent) -> bool:
        """Handle 'academics.quiz.finished' event to update topic stats and streak.

        Returns:
            True if event was processed, False if already processed (idempotent).
        """
        payload = event.payload
        raw_uid = payload.get("user_id")
        if not raw_uid:
            # Anonymous quiz sessions do not maintain persistent topic stats
            return True

        user_id = uuid.UUID(raw_uid)
        score = int(payload.get("score", 0))
        total_questions = int(payload.get("total_questions", 0))
        topic_key = str(payload.get("topic_key", "general_science"))
        topic_name = str(payload.get("topic_name", "General Science"))

        async with UnitOfWork(self._session_factory) as uow:
            progress_repo: ProgressPort = SQLAlchemyProgressRepository(uow.session)
            bank_repo: QuestionBankPort = SQLAlchemyQuestionBank(uow.session)

            # 1. Record activity log idempotently
            recorded = await progress_repo.record_activity(
                user_id=user_id,
                activity_type="quiz",
                event_id=event.id,
                created_at=event.created_at,
                meta=payload,
            )
            if not recorded:
                # Already processed
                return False

            # 2. Get or create topic
            topic = await bank_repo.get_or_create_topic(topic_key, topic_name)

            # 3. Update topic statistics
            await progress_repo.update_topic_stats(
                user_id=user_id,
                topic_id=topic.id,
                attempts_delta=total_questions,
                correct_delta=score,
                timestamp=event.created_at,
            )
            return True

    async def handle_flashcard_graded(self, event: DomainEvent) -> bool:
        """Handle 'academics.flashcard.graded' event to update deck topic stats and streak.

        Returns:
            True if event was processed, False if already processed (idempotent).
        """
        payload = event.payload
        raw_uid = payload.get("user_id")
        if not raw_uid:
            return True

        user_id = uuid.UUID(raw_uid)
        rating = str(payload.get("rating", ""))
        raw_deck_id = payload.get("deck_id")
        if not raw_deck_id:
            return True

        deck_id = uuid.UUID(raw_deck_id)
        is_correct = 1 if rating in ("good", "easy") else 0

        async with UnitOfWork(self._session_factory) as uow:
            progress_repo: ProgressPort = SQLAlchemyProgressRepository(uow.session)
            bank_repo: QuestionBankPort = SQLAlchemyQuestionBank(uow.session)

            # 1. Record activity log idempotently
            recorded = await progress_repo.record_activity(
                user_id=user_id,
                activity_type="flashcard",
                event_id=event.id,
                created_at=event.created_at,
                meta=payload,
            )
            if not recorded:
                return False

            # 2. Resolve topic name from Deck
            deck = await uow.session.get(Deck, deck_id)
            deck_name = deck.name if deck else "Flashcards"
            topic_key, display_name = normalize_topic(deck_name)

            topic = await bank_repo.get_or_create_topic(topic_key, display_name)

            # 3. Update topic statistics
            await progress_repo.update_topic_stats(
                user_id=user_id,
                topic_id=topic.id,
                attempts_delta=1,
                correct_delta=is_correct,
                timestamp=event.created_at,
            )
            return True

    # ---------------------------------------------------------------------------
    # Progress Report Query
    # ---------------------------------------------------------------------------

    async def get_progress_report(
        self,
        user_id: uuid.UUID,
        scope: ProgressScope = "summary",
        user_timezone: str = "UTC",
    ) -> tuple[str, ProgressReportResponseData, list[str]]:
        """Generate structured progress report and voice summary for a student.

        Returns:
            Tuple of (spoken_summary, response_data, next_actions).
        """
        today = resolve_current_date(self._clock, user_timezone=user_timezone)
        now = self._clock()

        async with UnitOfWork(self._session_factory) as uow:
            progress_repo: ProgressPort = SQLAlchemyProgressRepository(uow.session)

            # 1. Query timestamps and calculate streak
            timestamps = await progress_repo.get_activity_timestamps(user_id)
            activity_dates = timestamps_to_dates(timestamps, user_timezone=user_timezone)
            streak: StreakInfo = calculate_streak(activity_dates, today=today)

            # 2. Query topic stats and calculate weak topics
            db_stats = await progress_repo.get_topic_stats(user_id)
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
            weak_topics_data = [
                WeakTopicData(
                    topic=w.topic,
                    attempts=w.attempts,
                    correct=w.correct,
                    accuracy_pct=w.accuracy_pct,
                )
                for w in weak_summaries
            ]

            # 3. Query all-time quiz performance
            (
                quizzes_count,
                total_q,
                correct_q,
            ) = await progress_repo.get_quiz_performance_summary(user_id)
            if quizzes_count == 0 and total_q == 0 and topic_summaries:
                # Fallback to accumulated topic statistics if individual quiz rows are pruned
                total_q = sum(t.attempts for t in topic_summaries)
                correct_q = sum(t.correct for t in topic_summaries)
                quizzes_count = len(activity_dates) if activity_dates else len(topic_summaries)

            overall_acc = round((correct_q / total_q) * 100.0, 1) if total_q > 0 else 0.0

            # 4. Weekly metrics (past 7 days) if needed
            weekly_data: WeeklySummaryData | None = None
            seven_days_ago = now - timedelta(days=7)
            (
                w_quizzes,
                w_questions,
                w_correct,
            ) = await progress_repo.get_quiz_performance_summary(user_id, since=seven_days_ago)
            w_cards = await progress_repo.get_cards_reviewed_count(user_id, since=seven_days_ago)
            seven_day_dates = {d for d in activity_dates if today - timedelta(days=6) <= d <= today}
            if w_quizzes == 0 and w_questions == 0 and seven_day_dates and topic_summaries:
                w_questions = sum(t.attempts for t in topic_summaries)
                w_correct = sum(t.correct for t in topic_summaries)
                w_quizzes = len(seven_day_dates)

            weekly_domain = calculate_weekly_summary(
                activity_dates=activity_dates,
                today=today,
                quizzes_completed=w_quizzes,
                questions_answered=w_questions,
                correct_count=w_correct,
                cards_reviewed=w_cards,
            )
            weekly_data = WeeklySummaryData(
                active_days=weekly_domain.active_days,
                quizzes_completed=weekly_domain.quizzes_completed,
                questions_answered=weekly_domain.questions_answered,
                correct_count=weekly_domain.correct_count,
                accuracy_pct=weekly_domain.accuracy_pct,
                cards_reviewed=weekly_domain.cards_reviewed,
            )

        streak_data = StreakData(
            current_streak=streak.current_streak,
            longest_streak=streak.longest_streak,
            studied_today=streak.studied_today,
            last_active_date=streak.last_active_date.isoformat()
            if streak.last_active_date
            else None,
        )

        # 5. Format scope-specific response and spoken summary
        if scope == "weak_topics":
            spoken = format_weak_topics_spoken(weak_summaries)
            next_actions = ["Say 'quiz me on my weak topics' to practice."]
        elif scope == "streak":
            spoken = format_streak_spoken(streak)
            next_actions = ["Say 'quiz me on science' to keep your study streak."]
        elif scope == "weekly":
            spoken = format_weekly_spoken(weekly_domain)
            next_actions = ["Say 'what are my weak topics' to check areas needing practice."]
        else:  # summary
            top_weak = weak_summaries[0].topic if weak_summaries else None
            spoken = format_summary_spoken(
                quizzes_count=quizzes_count,
                questions_count=total_q,
                accuracy_pct=overall_acc,
                streak_days=streak.current_streak,
                weakest_topic=top_weak,
            )
            next_actions = [
                "Say 'quiz me on my weak topics' to practice.",
                "Say 'review flashcards' to review cards.",
            ]

        response_data = ProgressReportResponseData(
            scope=scope,
            streak=streak_data,
            total_quizzes=quizzes_count,
            total_questions=total_q,
            total_correct=correct_q,
            accuracy_pct=overall_acc,
            weak_topics=weak_topics_data,
            weekly=weekly_data,
        )

        return spoken, response_data, next_actions
