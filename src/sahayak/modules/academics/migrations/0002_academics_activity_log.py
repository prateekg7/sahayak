"""Create activity_log table in academics schema for streak tracking and event idempotency.

Revision ID: 0002_academics_activity_log
Revises: 0001_academics_schema
Create Date: 2026-10-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_academics_activity_log"
down_revision = "0001_academics_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create academics.activity_log table and indexes."""
    op.create_table(
        "activity_log",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("core.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("activity_type", sa.String(length=64), nullable=False),
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            unique=True,
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        schema="academics",
    )
    op.create_index(
        "ix_academics_activity_log_user_created",
        "activity_log",
        ["user_id", "created_at"],
        schema="academics",
    )


def downgrade() -> None:
    """Drop academics.activity_log table and indexes."""
    op.drop_index(
        "ix_academics_activity_log_user_created",
        table_name="activity_log",
        schema="academics",
    )
    op.drop_table("activity_log", schema="academics")
