"""Quiz domain service managing quiz sessions, question loading, and turn orchestration."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from sahayak.core.db.session import SessionFactory, UnitOfWork
from sahayak.core.errors import (
    ForbiddenError,
    InvalidInputError,
    NotFoundError,
    UpstreamUnavailableError,
)
from sahayak.core.events import publish as publish_event
from sahayak.modules.academics.adapters.generation import QuestionGenerationPipeline
from sahayak.modules.academics.adapters.question_bank import SQLAlchemyQuestionBank
from sahayak.modules.academics.domain.answer_matching import match_spoken_answer
from sahayak.modules.academics.domain.scoring import (
    calculate_quiz_score_percentage,
    evaluate_answer,
    is_quiz_expired,
    is_quiz_finished,
)
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


@dataclass(frozen=True)
class AnsweredQuizInfo:
    """Result of evaluating a submitted quiz answer."""

    quiz_id: uuid.UUID
    correct: bool
    correct_key: str
    explanation: str
    score_correct: int
    score_answered: int
    score_total: int
    finished: bool
    spoken_summary: str
    next_number: int | None = None
    next_question: str | None = None
    next_options: dict[str, str] | None = None
    final_summary: str | None = None


JobEnqueuer = Callable[..., Awaitable[Any]]


class QuizService:
    """Service orchestrating quiz creation, question fetching/generation, and scoring."""

    def __init__(
        self,
        session_factory: SessionFactory,
        generator: QuestionGenerationPipeline | None = None,
        clock: Callable[[], datetime] | None = None,
        quiz_ttl_minutes: int = DEFAULT_QUIZ_TTL_MINUTES,
        enqueuer: JobEnqueuer | None = None,
        bank_min_threshold: int = 10,
    ) -> None:
        self._session_factory = session_factory
        self._generator = generator
        self._clock = clock or (lambda: datetime.now(UTC))
        self._quiz_ttl_minutes = quiz_ttl_minutes
        self._enqueuer = enqueuer
        self._bank_min_threshold = bank_min_threshold

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
                    .where(TopicStats.user_id == user_id, TopicStats.attempts > 0)
                    .order_by(
                        (TopicStats.correct * 1.0 / TopicStats.attempts).asc(),
                        TopicStats.attempts.desc(),
                    )
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
            is_miss = len(available_questions) < clamped_count

            # 5. Fallback synchronous generation on cache miss
            if is_miss and self._generator is not None:
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

            # 5b. Trigger background bank expansion and prefetch on miss or low bank reserves
            low_reserve = len(available_questions) < self._bank_min_threshold
            if (is_miss or low_reserve) and self._enqueuer is not None:
                try:
                    await self._enqueuer("academics_expand_bank", topic_key, diff_enum.value)
                    await self._enqueuer("academics_prefetch_adjacent", topic_key, diff_enum.value)
                except Exception as exc:
                    logger.debug("Background bank expansion enqueue ignored: %s", exc)

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

    async def answer_question(
        self,
        user_id: uuid.UUID | None,
        quiz_id: str | uuid.UUID,
        answer_text: str,
    ) -> AnsweredQuizInfo:
        """Evaluate an answer to the active question in a quiz session."""
        if isinstance(quiz_id, str):
            try:
                quiz_uuid = uuid.UUID(quiz_id)
            except ValueError as err:
                raise InvalidInputError(
                    spoken=(
                        "The quiz ID provided is invalid. "
                        "Please start a new quiz by saying 'start a quiz'."
                    ),
                    detail=f"Invalid quiz UUID: {quiz_id}",
                ) from err
        else:
            quiz_uuid = quiz_id

        async with UnitOfWork(self._session_factory) as uow:
            # 1. Fetch quiz with related questions and topic
            stmt = (
                select(Quiz)
                .options(
                    selectinload(Quiz.quiz_questions).selectinload(QuizQuestion.question),
                    selectinload(Quiz.topic),
                )
                .where(Quiz.id == quiz_uuid)
            )
            res = await uow.session.execute(stmt)
            quiz = res.scalar_one_or_none()

            if quiz is None:
                raise NotFoundError(
                    spoken=(
                        "I couldn't find an active quiz session. "
                        "You can say 'start a quiz' to begin."
                    ),
                    detail=f"Quiz {quiz_uuid} not found",
                )

            # 2. Check ownership: if quiz was started by an authenticated user, caller must match
            if quiz.user_id is not None and (user_id is None or user_id != quiz.user_id):
                raise ForbiddenError(
                    spoken="You don't have permission to access this quiz session.",
                    detail=f"Quiz user {quiz.user_id} does not match caller {user_id}",
                )

            # 3. Check status and expiry
            now = self._clock()
            if quiz.status == QuizStatus.COMPLETED:
                raise InvalidInputError(
                    spoken=(
                        "This quiz has already been completed. Say 'start a quiz' to play again."
                    ),
                    detail=f"Quiz {quiz_uuid} is already COMPLETED",
                )

            if is_quiz_expired(quiz.expires_at, now) or quiz.status == QuizStatus.EXPIRED:
                quiz.status = QuizStatus.EXPIRED
                await uow.session.commit()
                raise NotFoundError(
                    spoken="This quiz session has expired. Say 'start a quiz' to begin a new one.",
                    detail=f"Quiz {quiz_uuid} expired at {quiz.expires_at}",
                )

            # 4. Resolve current question
            ordered_qqs = sorted(quiz.quiz_questions, key=lambda qq: qq.position)
            if quiz.current_index >= len(ordered_qqs):
                quiz.status = QuizStatus.COMPLETED
                await uow.session.commit()
                raise InvalidInputError(
                    spoken="All questions in this quiz have already been answered.",
                    detail=f"Quiz current_index {quiz.current_index} >= {len(ordered_qqs)}",
                )

            current_qq = ordered_qqs[quiz.current_index]
            current_q = current_qq.question

            # 5. Spoken answer matching
            options = current_q.options or {}
            match_res = match_spoken_answer(spoken_answer=answer_text, options=options)

            if match_res.is_ambiguous:
                # Ambiguous answer does NOT consume attempt or advance question
                raise InvalidInputError(
                    spoken=(
                        "I'm not sure which option you meant. "
                        "Please say the letter or option text again."
                    ),
                    detail=(
                        f"Ambiguous answer '{answer_text}' for question {quiz.current_index + 1}"
                    ),
                )

            # 6. Evaluate correctness
            selected_key = match_res.matched_key
            is_correct = evaluate_answer(
                correct_key=current_q.correct_key,
                selected_key=selected_key,
            )

            # 7. Record attempt
            current_qq.selected_key = selected_key
            current_qq.is_correct = is_correct
            current_qq.answered_at = now

            if is_correct:
                quiz.score_correct += 1
            quiz.current_index += 1

            # 8. Update TopicStats if user is authenticated
            if quiz.user_id is not None:
                stats_stmt = select(TopicStats).where(
                    TopicStats.user_id == quiz.user_id,
                    TopicStats.topic_id == quiz.topic_id,
                )
                stats_res = await uow.session.execute(stats_stmt)
                stats = stats_res.scalar_one_or_none()
                if stats is None:
                    stats = TopicStats(
                        user_id=quiz.user_id,
                        topic_id=quiz.topic_id,
                        attempts=1,
                        correct=1 if is_correct else 0,
                        last_attempt_at=now,
                    )
                    uow.session.add(stats)
                else:
                    stats.attempts += 1
                    if is_correct:
                        stats.correct += 1
                    stats.last_attempt_at = now

            # 9. Check if quiz is finished
            finished = is_quiz_finished(quiz.current_index, quiz.total)
            next_number: int | None = None
            next_stem: str | None = None
            next_opts: dict[str, str] | None = None
            final_summary: str | None = None

            if finished:
                quiz.status = QuizStatus.COMPLETED
                quiz.finished_at = now

                pct = calculate_quiz_score_percentage(quiz.score_correct, quiz.total)
                final_summary = (
                    f"Quiz completed! You answered {quiz.score_correct} out of {quiz.total} "
                    f"questions correctly ({pct:.0f}%)."
                )

                # Publish domain event
                publish_event(
                    session=uow.session,
                    aggregate="quiz",
                    type="academics.quiz.finished",
                    payload={
                        "quiz_id": str(quiz.id),
                        "user_id": str(quiz.user_id) if quiz.user_id else None,
                        "topic_key": quiz.topic.topic_key,
                        "topic_name": quiz.topic.display_name,
                        "score": quiz.score_correct,
                        "total_questions": quiz.total,
                        "percentage": pct,
                    },
                )

                if is_correct:
                    spoken = (
                        f"That's correct! You finished the quiz with {quiz.score_correct} out of "
                        f"{quiz.total} correct, or {pct:.0f} percent. Great job!"
                    )
                else:
                    correct_opt_text = options.get(current_q.correct_key, "")
                    spoken = (
                        f"Not quite. The correct answer was {current_q.correct_key}, "
                        f"{correct_opt_text}. You finished the quiz with {quiz.score_correct} "
                        f"out of {quiz.total} correct, or {pct:.0f} percent."
                    )
            else:
                next_qq = ordered_qqs[quiz.current_index]
                next_q = next_qq.question
                next_number = quiz.current_index + 1
                next_stem = next_q.stem
                next_opts = next_q.options or {}

                correct_opt_text = options.get(current_q.correct_key, "")
                if is_correct:
                    feedback = "That's correct! "
                else:
                    feedback = (
                        f"Not quite. The correct answer was {current_q.correct_key}, "
                        f"{correct_opt_text}. "
                    )

                opts_str = ", ".join(f"{k}: {v}" for k, v in sorted(next_opts.items()))
                spoken = (
                    f"{feedback}Question {next_number} of {quiz.total}: {next_stem} "
                    f"Is it {opts_str}?"
                )
                if len(spoken) > MAX_SPOKEN_SUMMARY_CHARS:
                    spoken = f"{feedback}Question {next_number} of {quiz.total}: {next_stem}"
                    if len(spoken) > MAX_SPOKEN_SUMMARY_CHARS:
                        spoken = spoken[: MAX_SPOKEN_SUMMARY_CHARS - 3] + "..."

            await uow.session.commit()

            return AnsweredQuizInfo(
                quiz_id=quiz.id,
                correct=is_correct,
                correct_key=current_q.correct_key,
                explanation=current_q.explanation,
                score_correct=quiz.score_correct,
                score_answered=quiz.current_index,
                score_total=quiz.total,
                finished=finished,
                spoken_summary=spoken,
                next_number=next_number,
                next_question=next_stem,
                next_options=next_opts,
                final_summary=final_summary,
            )
