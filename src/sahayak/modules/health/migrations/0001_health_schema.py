"""Create health schema and entries table (T7.1).

Revision ID: 0001_health_schema
Revises:
Create Date: 2026-10-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_health_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create health schema and entries table."""
    op.execute("CREATE SCHEMA IF NOT EXISTS health")

    op.create_table(
        "entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("core.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "kind",
            sa.String(32),
            nullable=False,
            comment="Entry kind: water, meal, workout, sleep, or weight",
        ),
        sa.Column(
            "data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="Typed metric data for the given kind",
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default="false",
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
        "ix_health_entries_user_kind_occurred",
        "entries",
        ["user_id", "kind", "occurred_at"],
        schema="health",
    )


def downgrade() -> None:
    """Drop entries table and health schema."""
    op.drop_index(
        "ix_health_entries_user_kind_occurred",
        table_name="entries",
        schema="health",
    )
    op.drop_table("entries", schema="health")
    op.execute("DROP SCHEMA IF EXISTS health CASCADE")
