"""Academics feature module satisfying the Module protocol."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select

from sahayak.core.db.session import UnitOfWork
from sahayak.core.module import Deps, HealthStatus
from sahayak.modules.academics.models import Card, Deck, PlanTask, Quiz, StudyPlan, TopicStats


class AcademicsModule:
    """Academics module managing quizzes, flashcards, study plans, and topic statistics."""

    def __init__(self) -> None:
        self._deps: Deps | None = None

    @property
    def name(self) -> str:
        return "academics"

    @property
    def version(self) -> str:
        return "0.1.0"

    def register_tools(self, mcp: Any, deps: Deps) -> None:
        """Register MCP tools provided by the academics module."""
        self._deps = deps
        if deps.session_factory is not None:
            from sahayak.core.config import get_settings
            from sahayak.modules.academics.adapters.generation import QuestionGenerationPipeline
            from sahayak.modules.academics.adapters.verification import QuestionVerifier
            from sahayak.modules.academics.service.quiz import QuizService
            from sahayak.modules.academics.tools.quiz import set_quiz_service

            settings = get_settings()
            generator = None
            if deps.llm_client is not None:
                verifier = QuestionVerifier(llm_client=deps.llm_client)
                generator = QuestionGenerationPipeline(
                    llm_client=deps.llm_client,
                    verifier=verifier,
                )
            from sahayak.worker import enqueue_job

            async def safe_enqueue(job_name: str, *args: Any, **kwargs: Any) -> Any:
                try:
                    return await enqueue_job(job_name, *args, **kwargs)
                except Exception:
                    # In test environments without Redis or when worker is offline
                    return None

            service = QuizService(
                session_factory=deps.session_factory,
                generator=generator,
                quiz_ttl_minutes=settings.quiz_ttl_minutes,
                enqueuer=safe_enqueue,
                bank_min_threshold=settings.academics_bank_min_threshold,
            )
            set_quiz_service(service)

            from sahayak.modules.academics.service.flashcards import FlashcardService
            from sahayak.modules.academics.tools.flashcards import set_flashcard_service

            flashcard_service = FlashcardService(session_factory=deps.session_factory)
            set_flashcard_service(flashcard_service)

        from sahayak.modules.academics.tools.flashcards import (
            FLASHCARDS_DESCRIPTION,
            flashcards,
        )
        from sahayak.modules.academics.tools.quiz import (
            QUIZ_ANSWER_DESCRIPTION,
            QUIZ_START_DESCRIPTION,
            quiz_answer,
            quiz_start,
        )

        tool_decorator = getattr(mcp, "tool", None)
        if callable(tool_decorator):
            tool_decorator(name="quiz_start", description=QUIZ_START_DESCRIPTION)(quiz_start)
            tool_decorator(name="quiz_answer", description=QUIZ_ANSWER_DESCRIPTION)(quiz_answer)
            tool_decorator(name="flashcards", description=FLASHCARDS_DESCRIPTION)(flashcards)
        elif hasattr(mcp, "add_tool"):
            mcp.add_tool(quiz_start, name="quiz_start", description=QUIZ_START_DESCRIPTION)
            mcp.add_tool(quiz_answer, name="quiz_answer", description=QUIZ_ANSWER_DESCRIPTION)
            mcp.add_tool(flashcards, name="flashcards", description=FLASHCARDS_DESCRIPTION)

    def register_jobs(self, worker: Any) -> None:
        """Register background worker jobs owned by the academics module."""
        from sahayak.modules.academics.jobs import (
            expand_bank,
            expire_quizzes,
            popular_topics_pregen,
            prefetch_adjacent_difficulty,
        )

        worker.register_job(expand_bank, name="academics_expand_bank")
        worker.register_job(prefetch_adjacent_difficulty, name="academics_prefetch_adjacent")
        worker.register_cron(expire_quizzes, minute="*/5", name="academics_expire_quizzes")
        worker.register_cron(
            popular_topics_pregen,
            hour="*/6",
            minute=0,
            name="academics_popular_topics_pregen",
        )

    def migrations_path(self) -> str | None:
        """Return path to Alembic migrations for the academics branch."""
        return str(Path(__file__).parent / "migrations")

    def health(self) -> HealthStatus:
        """Self-check reporting module operational readiness."""
        return HealthStatus(healthy=True, detail="academics module ready")

    def on_event(self, event: Any) -> None:
        """Handle dispatched domain events."""
        # Event subscriptions will be wired in T3.13 (quiz.finished -> topic_stats)

    async def export_user_data(self, user_id: str) -> dict[str, Any]:
        """Return all academics data owned by the given user for privacy export."""
        if self._deps is None or self._deps.session_factory is None:
            return {}

        uid = uuid.UUID(user_id)
        async with UnitOfWork(self._deps.session_factory) as uow:
            # 1. Decks & Cards
            decks_res = await uow.session.execute(select(Deck).where(Deck.user_id == uid))
            decks = list(decks_res.scalars().all())

            cards_res = await uow.session.execute(select(Card).where(Card.user_id == uid))
            cards = list(cards_res.scalars().all())

            # 2. Study Plans & Tasks
            plans_res = await uow.session.execute(select(StudyPlan).where(StudyPlan.user_id == uid))
            plans = list(plans_res.scalars().all())

            # 3. Topic Stats
            stats_res = await uow.session.execute(
                select(TopicStats).where(TopicStats.user_id == uid)
            )
            stats = list(stats_res.scalars().all())

            # 4. Quizzes
            quizzes_res = await uow.session.execute(select(Quiz).where(Quiz.user_id == uid))
            quizzes = list(quizzes_res.scalars().all())

            return {
                "decks": [
                    {"id": str(d.id), "name": d.name, "created_at": d.created_at.isoformat()}
                    for d in decks
                ],
                "cards": [
                    {
                        "id": str(c.id),
                        "deck_id": str(c.deck_id),
                        "front": c.front,
                        "back": c.back,
                        "ease": c.ease,
                        "repetitions": c.repetitions,
                        "due_at": c.due_at.isoformat(),
                    }
                    for c in cards
                ],
                "study_plans": [
                    {
                        "id": str(p.id),
                        "goal": p.goal,
                        "exam_date": p.exam_date.isoformat(),
                        "created_at": p.created_at.isoformat(),
                    }
                    for p in plans
                ],
                "topic_stats": [
                    {
                        "topic_id": str(s.topic_id),
                        "attempts": s.attempts,
                        "correct": s.correct,
                        "last_attempt_at": s.last_attempt_at.isoformat(),
                    }
                    for s in stats
                ],
                "quizzes": [
                    {
                        "id": str(q.id),
                        "topic_id": str(q.topic_id),
                        "difficulty": q.difficulty.value,
                        "score_correct": q.score_correct,
                        "total": q.total,
                        "status": q.status.value,
                        "created_at": q.created_at.isoformat(),
                    }
                    for q in quizzes
                ],
            }

    async def delete_user_data(self, user_id: str) -> None:
        """Permanently delete all academics data associated with the given user."""
        if self._deps is None or self._deps.session_factory is None:
            return

        uid = uuid.UUID(user_id)
        async with UnitOfWork(self._deps.session_factory) as uow:
            # Cascading deletes clean up associated cards and plan tasks automatically
            await uow.session.execute(delete(Card).where(Card.user_id == uid))
            await uow.session.execute(delete(Deck).where(Deck.user_id == uid))
            await uow.session.execute(
                delete(PlanTask).where(
                    PlanTask.plan_id.in_(select(StudyPlan.id).where(StudyPlan.user_id == uid))
                )
            )
            await uow.session.execute(delete(StudyPlan).where(StudyPlan.user_id == uid))
            await uow.session.execute(delete(TopicStats).where(TopicStats.user_id == uid))
            await uow.session.execute(delete(Quiz).where(Quiz.user_id == uid))
            await uow.session.commit()


module = AcademicsModule()
