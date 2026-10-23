"""Create practice_sessions table in language schema (T11.2).

Revision ID: 0002_practice_sessions_schema
Revises: 0001_language_schema
Create Date: 2026-10-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_practice_sessions_schema"
down_revision = "0001_language_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create practice_sessions table."""
    op.create_table(
        "practice_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("core.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("language", sa.String(32), nullable=False),
        sa.Column("scenario", sa.String(64), nullable=False, server_default="general"),
        sa.Column("level", sa.String(32), nullable=False, server_default="beginner"),
        sa.Column("turns_completed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_turns", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column(
            "history",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        schema="language",
    )
    op.create_index(
        "ix_language_practice_sessions_user_status",
        "practice_sessions",
        ["user_id", "status"],
        schema="language",
    )
    op.create_index(
        "ix_language_practice_sessions_user_created",
        "practice_sessions",
        ["user_id", "created_at"],
        schema="language",
    )


def downgrade() -> None:
    """Drop practice_sessions table."""
    op.drop_index(
        "ix_language_practice_sessions_user_created",
        table_name="practice_sessions",
        schema="language",
    )
    op.drop_index(
        "ix_language_practice_sessions_user_status",
        table_name="practice_sessions",
        schema="language",
    )
    op.drop_table("practice_sessions", schema="language")
