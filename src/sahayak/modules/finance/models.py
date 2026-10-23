"""SQLAlchemy data models for the finance module (T6.1).

All monetary amounts are strictly persisted as integer minor units (PRD §1.2 Rule 4).
Zero floating-point representations are permitted.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
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


class Budget(Base):
    """Category budget record in finance.budgets table (T6.2)."""

    __tablename__ = "budgets"
    __table_args__ = (
        UniqueConstraint("user_id", "category", name="uq_finance_budgets_user_category"),
        Index("ix_finance_budgets_user_active", "user_id", "is_active"),
        {"schema": "finance"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="Normalized spending category",
    )
    amount_minor: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Monthly budget cap in integer minor units",
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="INR",
        server_default="INR",
        comment="ISO 4217 3-letter currency code",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
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
        """Convert budget to dictionary representation."""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "category": self.category,
            "amount_minor": self.amount_minor,
            "currency": self.currency,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Group(Base):
    """A bill-splitting group (e.g. 'Goa Trip', 'Roommates') owned by a user (T6.3)."""

    __tablename__ = "groups"
    __table_args__ = (
        Index("ix_finance_groups_user_id", "user_id"),
        {"schema": "finance"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="INR",
        server_default="INR",
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
            "name": self.name,
            "currency": self.currency,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class GroupMember(Base):
    """Named participant in a split group (does not require a separate user account)."""

    __tablename__ = "group_members"
    __table_args__ = (
        UniqueConstraint("group_id", "name", name="uq_finance_group_members_group_name"),
        {"schema": "finance"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("finance.groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        server_default=func.now(),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "group_id": str(self.group_id),
            "name": self.name,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class SharedExpense(Base):
    """A shared group expense with itemized participant split shares."""

    __tablename__ = "shared_expenses"
    __table_args__ = (
        Index("ix_finance_shared_expenses_group", "group_id"),
        {"schema": "finance"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("finance.groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    payer_name: Mapped[str] = mapped_column(String(64), nullable=False)
    total_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    split_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        server_default=func.now(),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "group_id": str(self.group_id),
            "payer_name": self.payer_name,
            "total_minor": self.total_minor,
            "description": self.description,
            "split_data": self.split_data,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Settlement(Base):
    """A recorded debt settlement payment between two group members."""

    __tablename__ = "settlements"
    __table_args__ = (
        Index("ix_finance_settlements_group", "group_id"),
        {"schema": "finance"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("finance.groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_name: Mapped[str] = mapped_column(String(64), nullable=False)
    to_name: Mapped[str] = mapped_column(String(64), nullable=False)
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    settled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        server_default=func.now(),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "group_id": str(self.group_id),
            "from_name": self.from_name,
            "to_name": self.to_name,
            "amount_minor": self.amount_minor,
            "settled_at": self.settled_at.isoformat() if self.settled_at else None,
        }


class Bill(Base):
    """Recurring bill or EMI due date record (T6.4)."""

    __tablename__ = "bills"
    __table_args__ = (
        Index("ix_finance_bills_user_due", "user_id", "next_due_date"),
        {"schema": "finance"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    amount_minor: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Due amount in integer minor units",
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="INR",
        server_default="INR",
    )
    frequency: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="monthly",
        server_default="monthly",
    )
    due_day: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Day of month or cycle date",
    )
    next_due_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )
    is_paid: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
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
            "name": self.name,
            "amount_minor": self.amount_minor,
            "currency": self.currency,
            "frequency": self.frequency,
            "due_day": self.due_day,
            "next_due_date": self.next_due_date.isoformat() if self.next_due_date else None,
            "is_paid": self.is_paid,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
