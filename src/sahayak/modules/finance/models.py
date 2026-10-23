"""SQLAlchemy data models for the finance module (T6.1).

All monetary amounts are strictly persisted as integer minor units (PRD §1.2 Rule 4).
Zero floating-point representations are permitted.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from sahayak.core.db.base import Base


class Expense(Base):
    """Personal expense record in finance.expenses table."""

    __tablename__ = "expenses"
    __table_args__ = (
        Index("ix_finance_expenses_user_occurred", "user_id", "occurred_at"),
        Index("ix_finance_expenses_user_category", "user_id", "category"),
        {"schema": "finance"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amount_minor: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Monetary value in integer minor units (e.g. 20000 for 200.00)",
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="INR",
        server_default="INR",
        comment="ISO 4217 3-letter currency code",
    )
    category: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="other",
        server_default="other",
    )
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        server_default=func.now(),
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        server_default=func.now(),
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert expense to dictionary representation."""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "amount_minor": self.amount_minor,
            "currency": self.currency,
            "category": self.category,
            "note": self.note,
            "occurred_at": self.occurred_at.isoformat() if self.occurred_at else None,
            "is_deleted": self.is_deleted,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
