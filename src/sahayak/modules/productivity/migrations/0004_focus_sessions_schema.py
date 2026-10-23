"""Create focus_sessions table in productivity schema (T5.4).

Revision ID: 0004_focus_sessions_schema
Revises: 0003_notes_schema
Create Date: 2026-10-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_focus_sessions_schema"
down_revision = "0003_notes_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create focus_sessions table and status/started_at indexes."""
    op.create_table(
        "focus_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("core.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("task_label", sa.String(255), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="25"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("planned_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actual_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        schema="productivity",
    )

    op.create_index(
        "ix_productivity_focus_sessions_user_status",
        "focus_sessions",
        ["user_id", "status"],
        schema="productivity",
    )

    op.create_index(
        "ix_productivity_focus_sessions_user_started",
        "focus_sessions",
        ["user_id", "started_at"],
        schema="productivity",
    )


def downgrade() -> None:
    """Drop focus_sessions table and indexes."""
    op.drop_index(
        "ix_productivity_focus_sessions_user_started",
        table_name="focus_sessions",
        schema="productivity",
    )
    op.drop_index(
        "ix_productivity_focus_sessions_user_status",
        table_name="focus_sessions",
        schema="productivity",
    )
    op.drop_table("focus_sessions", schema="productivity")
