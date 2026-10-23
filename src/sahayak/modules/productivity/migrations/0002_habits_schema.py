"""Create habits and habit_logs tables in productivity schema (T5.2).

Revision ID: 0002_habits_schema
Revises: 0001_productivity_schema
Create Date: 2026-10-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_habits_schema"
down_revision = "0001_productivity_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create habits and habit_logs tables and performance indexes."""
    op.create_table(
        "habits",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("core.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("target_frequency", sa.String(length=20), nullable=False, server_default="daily"),
        sa.Column("streak_current", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("streak_longest", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_logged_date", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        schema="productivity",
    )

    op.create_index(
        "ix_productivity_habits_user_archived",
        "habits",
        ["user_id", "archived_at"],
        schema="productivity",
    )

    op.create_table(
        "habit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "habit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("productivity.habits.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("core.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("logged_date", sa.Date(), nullable=False),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "habit_id", "logged_date", name="uq_productivity_habit_logs_habit_date"
        ),
        schema="productivity",
    )

    op.create_index(
        "ix_productivity_habit_logs_user_date",
        "habit_logs",
        ["user_id", "logged_date"],
        schema="productivity",
    )


def downgrade() -> None:
    """Drop habits and habit_logs tables and associated indexes."""
    op.drop_index(
        "ix_productivity_habit_logs_user_date",
        table_name="habit_logs",
        schema="productivity",
    )
    op.drop_table("habit_logs", schema="productivity")

    op.drop_index(
        "ix_productivity_habits_user_archived",
        table_name="habits",
        schema="productivity",
    )
    op.drop_table("habits", schema="productivity")
