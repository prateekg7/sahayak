"""Create medicines and medicine_doses tables in health schema (T7.2).

Revision ID: 0002_medicines_schema
Revises: 0001_health_schema
Create Date: 2026-10-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_medicines_schema"
down_revision = "0001_health_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create medicines and medicine_doses tables."""
    op.create_table(
        "medicines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("core.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "name",
            sa.String(128),
            nullable=False,
            comment="Medicine name as spoken by user",
        ),
        sa.Column(
            "dosage_text",
            sa.String(128),
            nullable=False,
            server_default="1 dose",
            comment="User-provided dosage description",
        ),
        sa.Column(
            "times",
            postgresql.JSONB,
            nullable=False,
            comment="List of scheduled times in HH:MM format",
        ),
        sa.Column(
            "days",
            postgresql.JSONB,
            nullable=True,
            comment="Optional list of active weekdays, e.g. ['mon', 'wed', 'fri']",
        ),
        sa.Column(
            "start_date",
            sa.Date(),
            nullable=False,
            server_default=sa.func.current_date(),
        ),
        sa.Column(
            "end_date",
            sa.Date(),
            nullable=True,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        schema="health",
    )
    op.create_index(
        "ix_health_medicines_user_active",
        "medicines",
        ["user_id", "is_active"],
        schema="health",
    )

    op.create_table(
        "medicine_doses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "medicine_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("health.medicines.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("core.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "scheduled_date",
            sa.Date(),
            nullable=False,
        ),
        sa.Column(
            "scheduled_time",
            sa.String(8),
            nullable=False,
            comment="Time in HH:MM format",
        ),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="pending",
            comment="Status: 'pending', 'taken', 'skipped', 'missed'",
        ),
        sa.Column(
            "taken_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "medicine_id",
            "scheduled_date",
            "scheduled_time",
            name="uq_health_doses_med_date_time",
        ),
        schema="health",
    )
    op.create_index(
        "ix_health_doses_user_date",
        "medicine_doses",
        ["user_id", "scheduled_date"],
        schema="health",
    )


def downgrade() -> None:
    """Drop medicine_doses and medicines tables."""
    op.drop_index("ix_health_doses_user_date", table_name="medicine_doses", schema="health")
    op.drop_table("medicine_doses", schema="health")
    op.drop_index("ix_health_medicines_user_active", table_name="medicines", schema="health")
    op.drop_table("medicines", schema="health")
