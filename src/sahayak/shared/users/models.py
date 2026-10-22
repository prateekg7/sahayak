"""Database models for platform users and external identities."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sahayak.core.db.base import Base


class User(Base):
    """Platform user representing an individual across identity providers."""

    __tablename__ = "users"
    __table_args__ = {"schema": "core"}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    locale: Mapped[str] = mapped_column(
        String(32), server_default="en-US", default="en-US", nullable=False
    )
    timezone: Mapped[str] = mapped_column(
        String(64), server_default="UTC", default="UTC", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    identities: Mapped[list[UserIdentity]] = relationship(
        "UserIdentity", back_populates="user", cascade="all, delete-orphan"
    )

    def __init__(self, **kwargs: object) -> None:
        """Initialize user with default UUID if not supplied."""
        kwargs.setdefault("id", uuid.uuid4())
        super().__init__(**kwargs)


class UserIdentity(Base):
    """Link between an external IdP subject and a platform user."""

    __tablename__ = "user_identities"
    __table_args__ = (
        UniqueConstraint("issuer", "subject", name="uq_user_identities_issuer_subject"),
        {"schema": "core"},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("core.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    issuer: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped[User] = relationship("User", back_populates="identities")

    def __init__(self, **kwargs: object) -> None:
        """Initialize identity with default UUID if not supplied."""
        kwargs.setdefault("id", uuid.uuid4())
        super().__init__(**kwargs)
