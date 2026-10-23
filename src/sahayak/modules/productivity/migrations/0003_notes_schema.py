"""Create notes table with full-text search index in productivity schema (T5.3).

Revision ID: 0003_notes_schema
Revises: 0002_habits_schema
Create Date: 2026-10-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_notes_schema"
down_revision = "0002_habits_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create notes table and full-text search index."""
    op.create_table(
        "notes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("core.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        schema="productivity",
    )

    op.create_index(
        "ix_productivity_notes_user_created",
        "notes",
        ["user_id", "created_at"],
        schema="productivity",
    )

    op.create_index(
        "ix_productivity_notes_content_tsv",
        "notes",
        [sa.text("to_tsvector('english', content)")],
        postgresql_using="gin",
        schema="productivity",
    )


def downgrade() -> None:
    """Drop notes table and indexes."""
    op.drop_index(
        "ix_productivity_notes_content_tsv",
        table_name="notes",
        schema="productivity",
        postgresql_using="gin",
    )
    op.drop_index(
        "ix_productivity_notes_user_created",
        table_name="notes",
        schema="productivity",
    )
    op.drop_table("notes", schema="productivity")
