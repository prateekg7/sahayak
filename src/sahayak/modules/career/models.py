"""SQLAlchemy data models for the career module (T8.1).

Mock interview sessions, evaluation turns, and performance rubrics.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from sahayak.core.db.base import Base


class InterviewSession(Base):
    """Mock interview practice session (T8.1)."""

    __tablename__ = "interview_sessions"
    __table_args__ = (
        Index("ix_career_sessions_user_status", "user_id", "status"),
        {"schema": "career"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="Target job role, e.g. 'Software Engineer' or 'Product Manager'",
    )
    level: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="mid",
        comment="Seniority level: 'junior', 'mid', 'senior', 'lead'",
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="in_progress",
        comment="Session status: 'in_progress', 'completed', 'abandoned'",
    )
    total_questions: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=5,
    )
    current_question_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    questions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        comment="List of interview questions and evaluation guidance",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        server_default=func.now(),
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "role": self.role,
            "level": self.level,
            "status": self.status,
            "total_questions": self.total_questions,
            "current_question_index": self.current_question_index,
            "questions": self.questions,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }


class InterviewTurn(Base):
    """An individual question-answer turn evaluated with rubric scoring (T8.1)."""

    __tablename__ = "interview_turns"
    __table_args__ = (
        UniqueConstraint("session_id", "question_index", name="uq_career_turns_session_q_idx"),
        Index("ix_career_turns_session", "session_id"),
        {"schema": "career"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("career.interview_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    question_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    question_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    user_answer: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    clarity_score: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Score 1-5 for structure and communication",
    )
    relevance_score: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Score 1-5 for addressing the prompt directly",
    )
    depth_score: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Score 1-5 for technical or situational depth",
    )
    feedback_tips: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        comment="Specific actionable improvement tips (max 2)",
    )
    feedback_spoken: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Concise voice spoken feedback string",
    )
    prompt_version: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="v1",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        server_default=func.now(),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "session_id": str(self.session_id),
            "question_index": self.question_index,
            "question_text": self.question_text,
            "user_answer": self.user_answer,
            "clarity_score": self.clarity_score,
            "relevance_score": self.relevance_score,
            "depth_score": self.depth_score,
            "feedback_tips": self.feedback_tips,
            "feedback_spoken": self.feedback_spoken,
            "prompt_version": self.prompt_version,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Application(Base):
    """Job application tracker entity (T8.2)."""

    __tablename__ = "applications"
    __table_args__ = (
        Index("ix_career_apps_user_status", "user_id", "status"),
        Index("ix_career_apps_user_follow_up", "user_id", "follow_up_at"),
        {"schema": "career"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    company: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="Company name, e.g. 'Google' or 'Stripe'",
    )
    role: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="Job title / role applied for",
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="applied",
        comment="Application status: applied, screening, interviewing, offer, rejected, withdrawn",
    )
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        server_default=func.now(),
    )
    follow_up_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default=None,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        server_default=func.now(),
        onupdate=func.now(),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "company": self.company,
            "role": self.role,
            "status": self.status,
            "applied_at": self.applied_at.isoformat() if self.applied_at else None,
            "follow_up_at": self.follow_up_at.isoformat() if self.follow_up_at else None,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class DailyPractice(Base):
    """Daily career practice question record (T8.3)."""

    __tablename__ = "daily_practice"
    __table_args__ = (
        Index("ix_career_practice_user_key", "user_id", "question_key"),
        Index("ix_career_practice_user_created", "user_id", "created_at"),
        {"schema": "career"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_key: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="Deterministic identifier of the question",
    )
    question_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    user_answer: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    is_correct: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    feedback: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        server_default=func.now(),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "question_key": self.question_key,
            "question_text": self.question_text,
            "user_answer": self.user_answer,
            "is_correct": self.is_correct,
            "feedback": self.feedback,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
