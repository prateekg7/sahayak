"""SQLAlchemy models for language learning module (T11.1)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sahayak.core.db.base import Base


class Word(Base):
    """Vocabulary word cache entry."""

    __tablename__ = "words"
    __table_args__ = (
        UniqueConstraint("language", "word", name="uq_language_words_lang_word"),
        Index("ix_language_words_lang_level", "language", "level"),
        {"schema": "language"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    language: Mapped[str] = mapped_column(String(32), nullable=False)
    level: Mapped[str] = mapped_column(
        String(32), nullable=False, default="beginner", server_default="beginner"
    )
    word: Mapped[str] = mapped_column(String(128), nullable=False)
    translation: Mapped[str] = mapped_column(String(255), nullable=False)
    pronunciation_hint: Mapped[str] = mapped_column(String(255), nullable=False)
    example_sentence: Mapped[str] = mapped_column(String(512), nullable=False)
    example_translation: Mapped[str] = mapped_column(String(512), nullable=False)
    part_of_speech: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert word to serializable dictionary."""
        return {
            "id": str(self.id),
            "language": self.language,
            "level": self.level,
            "word": self.word,
            "translation": self.translation,
            "pronunciation_hint": self.pronunciation_hint,
            "example_sentence": self.example_sentence,
            "example_translation": self.example_translation,
            "part_of_speech": self.part_of_speech,
            "created_at": self.created_at.isoformat(),
        }


class UserWord(Base):
    """User-specific learned vocabulary with SuperMemo-2 (SM-2) spaced repetition state."""

    __tablename__ = "user_words"
    __table_args__ = (
        UniqueConstraint("user_id", "word_id", name="uq_language_user_words"),
        Index("ix_language_user_words_user_due", "user_id", "due_at"),
        {"schema": "language"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    word_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("language.words.id", ondelete="CASCADE"),
        nullable=False,
    )
    ease: Mapped[float] = mapped_column(Float, nullable=False, default=2.5, server_default="2.5")
    interval_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    repetitions: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )

    word: Mapped[Word] = relationship("Word", lazy="joined")

    def to_dict(self) -> dict[str, Any]:
        """Convert user word state to dictionary."""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "word_id": str(self.word_id),
            "ease": self.ease,
            "interval_days": self.interval_days,
            "repetitions": self.repetitions,
            "due_at": self.due_at.isoformat(),
            "last_reviewed_at": (
                self.last_reviewed_at.isoformat() if self.last_reviewed_at else None
            ),
            "created_at": self.created_at.isoformat(),
            "word": self.word.to_dict() if self.word else None,
        }
