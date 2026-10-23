"""SQLAlchemy models for home and family module: households, memberships, invites (T9.1)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from sahayak.core.db.base import Base


class Household(Base):
    """Household entity representing a shared family or living unit (T9.1)."""

    __tablename__ = "households"
    __table_args__ = (
        Index("ix_home_households_creator", "created_by"),
        {"schema": "home"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="Name of the household (e.g. 'Baker Street')",
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.users.id", ondelete="CASCADE"),
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
            "name": self.name,
            "created_by": str(self.created_by),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class HouseholdMembership(Base):
    """Membership connecting a user to a household with owner/member role (T9.1)."""

    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("household_id", "user_id", name="uq_home_membership_household_user"),
        Index("ix_home_memberships_user", "user_id"),
        Index("ix_home_memberships_household", "household_id"),
        {"schema": "home"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    household_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("home.households.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="member",
        comment="Household role: 'owner' or 'member'",
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        server_default=func.now(),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "household_id": str(self.household_id),
            "user_id": str(self.user_id),
            "role": self.role,
            "joined_at": self.joined_at.isoformat() if self.joined_at else None,
        }


class HouseholdInvite(Base):
    """Expiring single-use invite code for household onboarding (T9.1)."""

    __tablename__ = "invites"
    __table_args__ = (
        UniqueConstraint("code", name="uq_home_invites_code"),
        Index("ix_home_invites_household", "household_id"),
        Index("ix_home_invites_code", "code"),
        {"schema": "home"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    household_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("home.households.id", ondelete="CASCADE"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment="6-character uppercase alphanumeric code",
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        server_default=func.now(),
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
    used_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.users.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "household_id": str(self.household_id),
            "code": self.code,
            "created_by": str(self.created_by),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "used_at": self.used_at.isoformat() if self.used_at else None,
            "used_by": str(self.used_by) if self.used_by else None,
        }


class SharedList(Base):
    """Shared list entity (e.g., 'shopping', 'groceries', 'hardware') (T9.2)."""

    __tablename__ = "lists"
    __table_args__ = (
        UniqueConstraint("household_id", "name", name="uq_home_lists_household_name"),
        Index("ix_home_lists_household", "household_id"),
        {"schema": "home"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    household_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("home.households.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default="shopping",
        comment="Normalized list name (e.g. 'shopping', 'groceries')",
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
            "household_id": str(self.household_id),
            "name": self.name,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class SharedListItem(Base):
    """Individual item on a shared list (T9.2)."""

    __tablename__ = "list_items"
    __table_args__ = (
        Index("ix_home_list_items_list_checked", "list_id", "checked"),
        {"schema": "home"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    list_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("home.lists.id", ondelete="CASCADE"),
        nullable=False,
    )
    item_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="Normalized name of item (e.g. 'Whole Milk')",
    )
    quantity: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        default=None,
        comment="Optional quantity description (e.g. '2 liters', '1 box')",
    )
    checked: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    added_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.users.id", ondelete="SET NULL"),
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
            "list_id": str(self.list_id),
            "item_name": self.item_name,
            "quantity": self.quantity,
            "checked": self.checked,
            "added_by": str(self.added_by) if self.added_by else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
