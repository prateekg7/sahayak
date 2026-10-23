"""Create career daily practice table (T8.3).

Revision ID: 0003_practice_schema
Revises: 0002_applications_schema
Create Date: 2026-10-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_practice_schema"
down_revision = "0002_applications_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create career.daily_practice table with user indexes."""
    op.create_table(
        "daily_practice",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("core.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("question_key", sa.String(64), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("user_answer", sa.Text(), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("feedback", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        schema="career",
    )

    op.create_index(
        "ix_career_practice_user_key",
        "daily_practice",
        ["user_id", "question_key"],
        schema="career",
    )
    op.create_index(
        "ix_career_practice_user_created",
        "daily_practice",
        ["user_id", "created_at"],
        schema="career",
    )


def downgrade() -> None:
    """Drop career.daily_practice table."""
    op.drop_index("ix_career_practice_user_created", table_name="daily_practice", schema="career")
    op.drop_index("ix_career_practice_user_key", table_name="daily_practice", schema="career")
    op.drop_table("daily_practice", schema="career")
