"""SQLAlchemy 2.0 database models for the Academics module."""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sahayak.core.db.base import Base


class DifficultyLevel(enum.StrEnum):
    """Normalized question and quiz difficulty levels."""

    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class QuestionStatus(enum.StrEnum):
    """Quality and quarantine status of a question in the bank."""

    APPROVED = "approved"
    FLAGGED = "flagged"
    QUARANTINED = "quarantined"


class QuizStatus(enum.StrEnum):
    """Lifecycle status of a student's quiz session."""

    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABANDONED = "abandoned"
    EXPIRED = "expired"


def _enum_values(enum_cls: Any) -> list[str]:
    """Extract string values from Enum class for PostgreSQL native enum mapping."""
    return [e.value for e in enum_cls]


class Topic(Base):
    """Normalized academic topic or subject."""

    __tablename__ = "topics"
    __table_args__ = {"schema": "academics"}

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    topic_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    questions: Mapped[list[Question]] = relationship("Question", back_populates="topic")

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("id", uuid.uuid4())
        kwargs.setdefault("created_at", datetime.now(UTC))
        super().__init__(**kwargs)


class Question(Base):
    """Individual multiple-choice question in the question bank."""

    __tablename__ = "questions"
    __table_args__ = (
        Index("ix_academics_questions_lookup", "topic_id", "difficulty", "status"),
        {"schema": "academics"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    topic_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("academics.topics.id", ondelete="CASCADE"),
        nullable=False,
    )
    difficulty: Mapped[DifficultyLevel] = mapped_column(
        Enum(
            DifficultyLevel,
            name="difficulty_level",
            schema="academics",
            native_enum=True,
            values_callable=_enum_values,
        ),
        nullable=False,
    )
    stem: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    correct_key: Mapped[str] = mapped_column(String(1), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    source_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[QuestionStatus] = mapped_column(
        Enum(
            QuestionStatus,
            name="question_status",
            schema="academics",
            native_enum=True,
            values_callable=_enum_values,
        ),
        default=QuestionStatus.APPROVED,
        nullable=False,
    )
    flag_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    topic: Mapped[Topic] = relationship("Topic", back_populates="questions")

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("id", uuid.uuid4())
        kwargs.setdefault("status", QuestionStatus.APPROVED)
        kwargs.setdefault("flag_count", 0)
        kwargs.setdefault("created_at", datetime.now(UTC))
        super().__init__(**kwargs)


class Quiz(Base):
    """A quiz session instance bound to a topic, user, and expiry."""

    __tablename__ = "quizzes"
    __table_args__ = (
        Index("ix_academics_quizzes_user_status", "user_id", "status"),
        {"schema": "academics"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("core.users.id", ondelete="SET NULL"),
        nullable=True,
    )
    topic_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("academics.topics.id", ondelete="CASCADE"),
        nullable=False,
    )
    difficulty: Mapped[DifficultyLevel] = mapped_column(
        Enum(
            DifficultyLevel,
            name="difficulty_level",
            schema="academics",
            native_enum=True,
            values_callable=_enum_values,
        ),
        nullable=False,
    )
    total: Mapped[int] = mapped_column(Integer, nullable=False)
    current_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[QuizStatus] = mapped_column(
        Enum(
            QuizStatus,
            name="quiz_status",
            schema="academics",
            native_enum=True,
            values_callable=_enum_values,
        ),
        default=QuizStatus.IN_PROGRESS,
        nullable=False,
    )
    score_correct: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    topic: Mapped[Topic] = relationship("Topic")
    quiz_questions: Mapped[list[QuizQuestion]] = relationship(
        "QuizQuestion",
        back_populates="quiz",
        order_by="QuizQuestion.position",
        cascade="all, delete-orphan",
    )

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("id", uuid.uuid4())
        kwargs.setdefault("current_index", 0)
        kwargs.setdefault("status", QuizStatus.IN_PROGRESS)
        kwargs.setdefault("score_correct", 0)
        kwargs.setdefault("created_at", datetime.now(UTC))
        super().__init__(**kwargs)


class QuizQuestion(Base):
    """Ordered question assignment within an active quiz session."""

    __tablename__ = "quiz_questions"
    __table_args__ = {"schema": "academics"}

    quiz_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("academics.quizzes.id", ondelete="CASCADE"),
        primary_key=True,
    )
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("academics.questions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    selected_key: Mapped[str | None] = mapped_column(String(1), nullable=True)
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    quiz: Mapped[Quiz] = relationship("Quiz", back_populates="quiz_questions")
    question: Mapped[Question] = relationship("Question")


class Deck(Base):
    """User-owned flashcard deck."""

    __tablename__ = "decks"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_academics_decks_user_name"),
        {"schema": "academics"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("core.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    cards: Mapped[list[Card]] = relationship(
        "Card", back_populates="deck", cascade="all, delete-orphan"
    )

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("id", uuid.uuid4())
        kwargs.setdefault("created_at", datetime.now(UTC))
        super().__init__(**kwargs)


class Card(Base):
    """Spaced-repetition flashcard adhering to the SM-2 algorithm."""

    __tablename__ = "cards"
    __table_args__ = (
        Index("ix_academics_cards_user_due", "user_id", "due_at"),
        {"schema": "academics"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    deck_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("academics.decks.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("core.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    front: Mapped[str] = mapped_column(Text, nullable=False)
    back: Mapped[str] = mapped_column(Text, nullable=False)
    ease: Mapped[float] = mapped_column(Float, default=2.5, nullable=False)
    interval_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    repetitions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    due_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    deck: Mapped[Deck] = relationship("Deck", back_populates="cards")

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("id", uuid.uuid4())
        kwargs.setdefault("ease", 2.5)
        kwargs.setdefault("interval_days", 0)
        kwargs.setdefault("repetitions", 0)
        kwargs.setdefault("due_at", datetime.now(UTC))
        kwargs.setdefault("created_at", datetime.now(UTC))
        super().__init__(**kwargs)


class StudyPlan(Base):
    """Exam-oriented study plan outlining preparation for a target date."""

    __tablename__ = "study_plans"
    __table_args__ = (
        Index("ix_academics_plans_user", "user_id"),
        {"schema": "academics"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("core.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    goal: Mapped[str] = mapped_column(String(256), nullable=False)
    exam_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    tasks: Mapped[list[PlanTask]] = relationship(
        "PlanTask", back_populates="plan", cascade="all, delete-orphan"
    )

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("id", uuid.uuid4())
        kwargs.setdefault("created_at", datetime.now(UTC))
        super().__init__(**kwargs)


class PlanTask(Base):
    """Dated daily task generated under a StudyPlan."""

    __tablename__ = "plan_tasks"
    __table_args__ = (
        Index("ix_academics_plan_tasks_plan_date", "plan_id", "date"),
        {"schema": "academics"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("academics.study_plans.id", ondelete="CASCADE"),
        nullable=False,
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    topic: Mapped[str] = mapped_column(String(256), nullable=False)
    minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    plan: Mapped[StudyPlan] = relationship("StudyPlan", back_populates="tasks")

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("id", uuid.uuid4())
        super().__init__(**kwargs)


class TopicStats(Base):
    """Aggregated quiz performance counters per user and topic."""

    __tablename__ = "topic_stats"
    __table_args__ = {"schema": "academics"}

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("core.users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    topic_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("academics.topics.id", ondelete="CASCADE"),
        primary_key=True,
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    correct: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("attempts", 0)
        kwargs.setdefault("correct", 0)
        kwargs.setdefault("last_attempt_at", datetime.now(UTC))
        super().__init__(**kwargs)


class ActivityLog(Base):
    """Transactional record of a student study activity for streak and progress calculation."""

    __tablename__ = "activity_log"
    __table_args__ = (
        Index("ix_academics_activity_log_user_created", "user_id", "created_at"),
        {"schema": "academics"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("core.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    activity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    event_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        unique=True,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("id", uuid.uuid4())
        kwargs.setdefault("created_at", datetime.now(UTC))
        super().__init__(**kwargs)
