"""Create career applications table (T8.2).

Revision ID: 0002_applications_schema
Revises: 0001_career_schema
Create Date: 2026-10-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_applications_schema"
down_revision = "0001_career_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create career.applications table with user indexes."""
    op.create_table(
        "applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("core.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("company", sa.String(128), nullable=False),
        sa.Column("role", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="applied"),
        sa.Column(
            "applied_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("follow_up_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
        schema="career",
    )

    op.create_index(
        "ix_career_apps_user_status",
        "applications",
        ["user_id", "status"],
        schema="career",
    )
    op.create_index(
        "ix_career_apps_user_follow_up",
        "applications",
        ["user_id", "follow_up_at"],
        schema="career",
    )


def downgrade() -> None:
    """Drop career.applications table."""
    op.drop_index("ix_career_apps_user_follow_up", table_name="applications", schema="career")
    op.drop_index("ix_career_apps_user_status", table_name="applications", schema="career")
    op.drop_table("applications", schema="career")
