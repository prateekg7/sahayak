"""Ports and interface definitions for Academics module repositories and external adapters."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date, datetime
from typing import Protocol

from sahayak.modules.academics.models import (
    Card,
    Deck,
    DifficultyLevel,
    PlanTask,
    Question,
    QuestionStatus,
    StudyPlan,
    Topic,
)

# Threshold of user flags before a question is automatically quarantined from serving
DEFAULT_QUARANTINE_THRESHOLD = 3


class QuestionBankPort(Protocol):
    """Repository port for academic topics and multiple-choice questions."""

    async def get_or_create_topic(self, topic_key: str, display_name: str) -> Topic:
        """Find an existing topic by canonical key or insert a new one."""
        ...

    async def find_topic(self, topic_key: str) -> Topic | None:
        """Find a topic by canonical key if it exists."""
        ...

    async def find_questions(
        self,
        topic_key: str,
        difficulty: DifficultyLevel,
        exclude_ids: Sequence[uuid.UUID] | None = None,
        status: QuestionStatus = QuestionStatus.APPROVED,
        limit: int = 5,
    ) -> Sequence[Question]:
        """Fetch available questions for a topic matching difficulty and status.

        Excludes question IDs already served or seen.
        """
        ...

    async def insert_questions(self, questions: Sequence[Question]) -> Sequence[Question]:
        """Persist questions into the bank with deduplication by content_hash.

        Returns the sequence of persisted questions.
        """
        ...

    async def count_available(
        self,
        topic_key: str,
        difficulty: DifficultyLevel,
        exclude_ids: Sequence[uuid.UUID] | None = None,
        status: QuestionStatus = QuestionStatus.APPROVED,
    ) -> int:
        """Count remaining available questions matching criteria."""
        ...

    async def flag_question(
        self,
        question_id: uuid.UUID,
        quarantine_threshold: int = DEFAULT_QUARANTINE_THRESHOLD,
    ) -> Question | None:
        """Increment flag_count on a question and quarantine if threshold is reached."""
        ...

    async def quarantine_question(self, question_id: uuid.UUID) -> Question | None:
        """Directly transition a question to quarantined status."""
        ...


class FlashcardPort(Protocol):
    """Repository port for flashcard decks and spaced repetition cards."""

    async def get_or_create_deck(self, user_id: uuid.UUID, name: str) -> Deck:
        """Find an existing deck by user and name, or create a new one."""
        ...

    async def find_deck(self, user_id: uuid.UUID, name: str) -> Deck | None:
        """Find a deck by user and name if it exists."""
        ...

    async def create_card(
        self,
        user_id: uuid.UUID,
        deck_id: uuid.UUID,
        front: str,
        back: str,
        due_at: datetime | None = None,
    ) -> Card:
        """Create and persist a new card in the given deck."""
        ...

    async def get_card(self, card_id: uuid.UUID, user_id: uuid.UUID) -> Card | None:
        """Retrieve a card ensuring user ownership."""
        ...

    async def get_next_due_card(
        self,
        user_id: uuid.UUID,
        deck_id: uuid.UUID | None = None,
        before: datetime | None = None,
    ) -> Card | None:
        """Fetch the single next due card for review ordered by due_at ASC."""
        ...

    async def list_due_cards(
        self,
        user_id: uuid.UUID,
        deck_id: uuid.UUID | None = None,
        before: datetime | None = None,
        limit: int = 5,
    ) -> Sequence[Card]:
        """Fetch due cards for review ordered by due_at ASC up to limit."""
        ...

    async def count_due_cards(
        self,
        user_id: uuid.UUID,
        deck_id: uuid.UUID | None = None,
        before: datetime | None = None,
    ) -> int:
        """Count total due cards for a user on or before the given timestamp."""
        ...

    async def save_card(self, card: Card) -> Card:
        """Persist updates to an existing card."""
        ...


class StudyPlanPort(Protocol):
    """Repository port for study plans and daily plan tasks."""

    async def create_plan(
        self,
        user_id: uuid.UUID,
        goal: str,
        exam_date: date,
        tasks: Sequence[PlanTask],
    ) -> StudyPlan:
        """Persist a new study plan and its associated initial tasks."""
        ...

    async def get_plan(self, plan_id: uuid.UUID, user_id: uuid.UUID) -> StudyPlan | None:
        """Retrieve a study plan ensuring user ownership."""
        ...

    async def get_active_plan(self, user_id: uuid.UUID, as_of: date) -> StudyPlan | None:
        """Fetch the latest active plan for a user whose exam_date >= as_of."""
        ...

    async def list_plans(self, user_id: uuid.UUID, limit: int = 5) -> Sequence[StudyPlan]:
        """List study plans for a user ordered by created_at DESC."""
        ...

    async def get_tasks_for_date(self, plan_id: uuid.UUID, target_date: date) -> Sequence[PlanTask]:
        """Fetch tasks for a plan on a specific calendar date."""
        ...

    async def get_task(
        self, task_id: uuid.UUID, plan_id: uuid.UUID | None = None
    ) -> PlanTask | None:
        """Fetch a specific plan task."""
        ...

    async def mark_task_done(self, task_id: uuid.UUID, done_at: datetime) -> PlanTask | None:
        """Mark a plan task as completed."""
        ...

    async def replace_future_tasks(
        self,
        plan_id: uuid.UUID,
        new_tasks: Sequence[PlanTask],
        from_date: date,
    ) -> Sequence[PlanTask]:
        """Delete incomplete tasks on or after from_date and insert new replanned tasks."""
        ...
