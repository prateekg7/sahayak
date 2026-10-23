"""SQLAlchemy data models for the health module (T7.1, T7.2).

Logging personal health metrics and medicine adherence only.
Zero medical advice provided (PRD §1.4).
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
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from sahayak.core.db.base import Base


class HealthEntry(Base):
    """Personal health metric log entry (water, meals, workouts, sleep, weight)."""

    __tablename__ = "entries"
    __table_args__ = (
        Index("ix_health_entries_user_kind_occurred", "user_id", "kind", "occurred_at"),
        {"schema": "health"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="Entry kind: water, meal, workout, sleep, or weight",
    )
    data: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="Typed metric data for the given kind",
    )
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
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "kind": self.kind,
            "data": self.data,
            "occurred_at": self.occurred_at.isoformat() if self.occurred_at else None,
            "is_deleted": self.is_deleted,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Medicine(Base):
    """Medicine schedule configured by user for adherence tracking (T7.2)."""

    __tablename__ = "medicines"
    __table_args__ = (
        Index("ix_health_medicines_user_active", "user_id", "is_active"),
        {"schema": "health"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="Medicine name as spoken by user",
    )
    dosage_text: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default="1 dose",
        comment="User-provided dosage description (e.g. '1 tablet')",
    )
    times: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        comment="List of scheduled times in HH:MM format, e.g. ['09:00', '21:00']",
    )
    days: Mapped[list[str] | None] = mapped_column(
        JSONB,
        nullable=True,
        default=None,
        comment="Optional list of active weekdays, e.g. ['mon', 'wed', 'fri']. None means daily.",
    )
    start_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        default=func.current_date(),
    )
    end_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        default=None,
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
            "dosage_text": self.dosage_text,
            "times": self.times,
            "days": self.days,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class MedicineDose(Base):
    """Scheduled and logged medicine dose for adherence reporting (T7.2)."""

    __tablename__ = "medicine_doses"
    __table_args__ = (
        UniqueConstraint(
            "medicine_id",
            "scheduled_date",
            "scheduled_time",
            name="uq_health_doses_med_date_time",
        ),
        Index("ix_health_doses_user_date", "user_id", "scheduled_date"),
        {"schema": "health"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    medicine_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("health.medicines.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scheduled_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )
    scheduled_time: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        comment="Time in HH:MM format",
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="pending",
        comment="Status: 'pending', 'taken', 'skipped', 'missed'",
    )
    taken_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
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
            "medicine_id": str(self.medicine_id),
            "user_id": str(self.user_id),
            "scheduled_date": self.scheduled_date.isoformat() if self.scheduled_date else None,
            "scheduled_time": self.scheduled_time,
            "status": self.status,
            "taken_at": self.taken_at.isoformat() if self.taken_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
