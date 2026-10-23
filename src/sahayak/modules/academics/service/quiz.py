"""Quiz domain service managing quiz sessions, question loading, and turn orchestration."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from sahayak.core.db.session import SessionFactory, UnitOfWork
from sahayak.core.errors import UpstreamUnavailableError
from sahayak.modules.academics.adapters.generation import QuestionGenerationPipeline
from sahayak.modules.academics.adapters.question_bank import SQLAlchemyQuestionBank
from sahayak.modules.academics.domain.topics import normalize_topic
from sahayak.modules.academics.models import (
    DifficultyLevel,
    Quiz,
    QuizQuestion,
    QuizStatus,
    Topic,
    TopicStats,
)
from sahayak.modules.academics.ports import QuestionBankPort

logger = logging.getLogger(__name__)

DEFAULT_QUIZ_TTL_MINUTES = 120
MAX_SPOKEN_SUMMARY_CHARS = 300


@dataclass(frozen=True)
class StartedQuizInfo:
    """Result of successfully initializing a new quiz session."""

    quiz_id: uuid.UUID
    topic_display_name: str
    difficulty: DifficultyLevel
    total_questions: int
    current_number: int
    stem: str
    options: dict[str, str]
    spoken_summary: str


class QuizService:
    """Service orchestrating quiz creation, question fetching/generation, and scoring."""

    def __init__(
        self,
        session_factory: SessionFactory,
        generator: QuestionGenerationPipeline | None = None,
        clock: Callable[[], datetime] | None = None,
        quiz_ttl_minutes: int = DEFAULT_QUIZ_TTL_MINUTES,
    ) -> None:
        self._session_factory = session_factory
        self._generator = generator
        self._clock = clock or (lambda: datetime.now(UTC))
        self._quiz_ttl_minutes = quiz_ttl_minutes

    async def start_quiz(
        self,
        user_id: uuid.UUID | None,
        topic: str | None = None,
        source: str = "topic",
        difficulty: str = "medium",
        num_questions: int = 5,
    ) -> StartedQuizInfo:
        """Initialize an interactive quiz session.

        Fetches approved questions from the local question bank. If insufficient
        questions exist in the bank, synchronously triggers the generation pipeline
        within the latency budget.
        """
        # 1. Clamp question count bounds
        clamped_count = max(3, min(10, num_questions))

        # 2. Parse difficulty
        try:
            diff_enum = DifficultyLevel(difficulty.lower().strip())
        except ValueError:
            diff_enum = DifficultyLevel.MEDIUM

        async with UnitOfWork(self._session_factory) as uow:
            bank: QuestionBankPort = SQLAlchemyQuestionBank(uow.session)

            # 3. Resolve target topic
            target_topic = topic
            if source == "weak_topics" and user_id is not None:
                # Query user's weakest topic from TopicStats
                weak_stmt = (
                    select(Topic)
                    .join(TopicStats, Topic.id == TopicStats.topic_id)
                    .where(TopicStats.user_id == user_id)
                    .order_by((TopicStats.correct * 1.0 / TopicStats.attempts).asc())
                    .limit(1)
                )
                weak_res = await uow.session.execute(weak_stmt)
                weak_topic = weak_res.scalar_one_or_none()
                if weak_topic is not None:
                    target_topic = weak_topic.display_name

            if not target_topic or not target_topic.strip():
                target_topic = "General Science"

            topic_key, display_name = normalize_topic(target_topic)
            topic_entity = await bank.get_or_create_topic(topic_key, display_name)

            # 4. Bank cache lookup
            available_questions = list(
                await bank.find_questions(
                    topic_key=topic_key,
                    difficulty=diff_enum,
                    limit=clamped_count,
                )
            )

            # 5. Fallback synchronous generation on cache miss
            if len(available_questions) < clamped_count and self._generator is not None:
                needed = clamped_count - len(available_questions)
                try:
                    gen_res = await self._generator.generate_questions(
                        topic=display_name,
                        difficulty=diff_enum,
                        count=needed,
                        topic_id=topic_entity.id,
                    )
                    if gen_res.questions:
                        await bank.insert_questions(gen_res.questions)
                        available_questions = list(
                            await bank.find_questions(
                                topic_key=topic_key,
                                difficulty=diff_enum,
                                limit=clamped_count,
                            )
                        )
                except Exception as exc:
                    logger.warning("Synchronous generation failed for '%s': %s", display_name, exc)

            if not available_questions:
                raise UpstreamUnavailableError(
                    spoken=(
                        f"I couldn't prepare quiz questions for {display_name} right now. "
                        "Please try another topic or ask again in a moment."
                    ),
                    detail=f"No questions available in bank for topic {topic_key}",
                )

            selected_questions = available_questions[:clamped_count]

            # 6. Create Quiz entity
            now = self._clock()
            expires_at = now + timedelta(minutes=self._quiz_ttl_minutes)

            quiz = Quiz(
                user_id=user_id,
                topic_id=topic_entity.id,
                difficulty=diff_enum,
                total=len(selected_questions),
                current_index=0,
                status=QuizStatus.IN_PROGRESS,
                score_correct=0,
                created_at=now,
                expires_at=expires_at,
            )
            uow.session.add(quiz)
            await uow.session.flush()

            # 7. Create QuizQuestion assignments
            for idx, q in enumerate(selected_questions):
                qq = QuizQuestion(
                    quiz_id=quiz.id,
                    position=idx + 1,
                    question_id=q.id,
                )
                uow.session.add(qq)

            await uow.session.commit()

            # 8. First question presentation (never leak correct answer)
            first_q = selected_questions[0]
            options = first_q.options or {}

            # Construct voice-first spoken summary
            opts_speech = ", ".join(f"{k}: {v}" for k, v in sorted(options.items()))
            spoken = (
                f"Starting a {quiz.total} question quiz on {display_name}. "
                f"Question 1: {first_q.stem} Is it {opts_speech}?"
            )
            if len(spoken) > MAX_SPOKEN_SUMMARY_CHARS:
                spoken = (
                    f"Starting a {quiz.total} question quiz on {display_name}. "
                    f"Question 1: {first_q.stem}"
                )

            return StartedQuizInfo(
                quiz_id=quiz.id,
                topic_display_name=display_name,
                difficulty=diff_enum,
                total_questions=quiz.total,
                current_number=1,
                stem=first_q.stem,
                options=options,
                spoken_summary=spoken,
            )
