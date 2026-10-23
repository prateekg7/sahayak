"""Create productivity schema and tasks table.

Revision ID: 0001_productivity_schema
Revises:
Create Date: 2026-10-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_productivity_schema"
down_revision = None
branch_labels = ("productivity",)
depends_on = ("0002_users_and_identities",)


def upgrade() -> None:
    """Create productivity schema, tasks table, and performance indexes."""
    op.execute("CREATE SCHEMA IF NOT EXISTS productivity")

    op.create_table(
        "tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("core.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("list_name", sa.String(length=100), nullable=False, server_default="inbox"),
        sa.Column("priority", sa.String(length=20), nullable=False, server_default="medium"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        schema="productivity",
    )

    op.create_index(
        "ix_productivity_tasks_user_status_due",
        "tasks",
        ["user_id", "status", "due_at"],
        schema="productivity",
    )
    op.create_index(
        "ix_productivity_tasks_user_list",
        "tasks",
        ["user_id", "list_name"],
        schema="productivity",
    )


def downgrade() -> None:
    """Drop tasks table and productivity schema."""
    op.drop_index(
        "ix_productivity_tasks_user_list",
        table_name="tasks",
        schema="productivity",
    )
    op.drop_index(
        "ix_productivity_tasks_user_status_due",
        table_name="tasks",
        schema="productivity",
    )
    op.drop_table("tasks", schema="productivity")
    op.execute("DROP SCHEMA IF EXISTS productivity CASCADE")
