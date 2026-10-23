"""SQLAlchemy models for the productivity schema (T5.1)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Date,
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


class Task(Base):
    """Task entity stored in productivity.tasks table."""

    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_productivity_tasks_user_status_due", "user_id", "status", "due_at"),
        Index("ix_productivity_tasks_user_list", "user_id", "list_name"),
        {"schema": "productivity"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    list_name: Mapped[str] = mapped_column(
        String(100), nullable=False, default="inbox", server_default="inbox"
    )
    priority: Mapped[str] = mapped_column(
        String(20), nullable=False, default="medium", server_default="medium"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tags: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now(), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def to_dict(self) -> dict[str, Any]:
        """Convert task to dictionary representation."""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "title": self.title,
            "list_name": self.list_name,
            "priority": self.priority,
            "status": self.status,
            "due_at": self.due_at.isoformat() if self.due_at else None,
            "tags": list(self.tags) if self.tags else [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class Habit(Base):
    """Habit entity stored in productivity.habits table."""

    __tablename__ = "habits"
    __table_args__ = (
        Index("ix_productivity_habits_user_archived", "user_id", "archived_at"),
        {"schema": "productivity"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    target_frequency: Mapped[str] = mapped_column(
        String(20), nullable=False, default="daily", server_default="daily"
    )
    streak_current: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    streak_longest: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_logged_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now(), server_default=func.now()
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def to_dict(self) -> dict[str, Any]:
        """Convert habit to dictionary representation."""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "name": self.name,
            "target_frequency": self.target_frequency,
            "streak_current": self.streak_current,
            "streak_longest": self.streak_longest,
            "last_logged_date": self.last_logged_date.isoformat()
            if self.last_logged_date
            else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "archived_at": self.archived_at.isoformat() if self.archived_at else None,
        }


class HabitLog(Base):
    """Historical completion log for a habit on a calendar date."""

    __tablename__ = "habit_logs"
    __table_args__ = (
        UniqueConstraint("habit_id", "logged_date", name="uq_productivity_habit_logs_habit_date"),
        Index("ix_productivity_habit_logs_user_date", "user_id", "logged_date"),
        {"schema": "productivity"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    habit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("productivity.habits.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    logged_date: Mapped[date] = mapped_column(Date, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now(), server_default=func.now()
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert habit log to dictionary representation."""
        return {
            "id": str(self.id),
            "habit_id": str(self.habit_id),
            "user_id": str(self.user_id),
            "logged_date": self.logged_date.isoformat(),
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Note(Base):
    """Voice note entity stored in productivity.notes table."""

    __tablename__ = "notes"
    __table_args__ = (
        Index("ix_productivity_notes_user_created", "user_id", "created_at"),
        {"schema": "productivity"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now(), server_default=func.now()
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert note to dictionary representation."""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "content": self.content,
            "tags": list(self.tags) if self.tags else [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
