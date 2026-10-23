"""Create language schema, words cache, and user_words spaced repetition table (T11.1).

Revision ID: 0001_language_schema
Revises:
Create Date: 2026-10-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_language_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create language schema and tables."""
    op.execute("CREATE SCHEMA IF NOT EXISTS language")

    # 1. words table
    op.create_table(
        "words",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("language", sa.String(32), nullable=False),
        sa.Column("level", sa.String(32), nullable=False, server_default="beginner"),
        sa.Column("word", sa.String(128), nullable=False),
        sa.Column("translation", sa.String(255), nullable=False),
        sa.Column("pronunciation_hint", sa.String(255), nullable=False),
        sa.Column("example_sentence", sa.String(512), nullable=False),
        sa.Column("example_translation", sa.String(512), nullable=False),
        sa.Column("part_of_speech", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("language", "word", name="uq_language_words_lang_word"),
        schema="language",
    )
    op.create_index(
        "ix_language_words_lang_level",
        "words",
        ["language", "level"],
        schema="language",
    )

    # 2. user_words table
    op.create_table(
        "user_words",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("core.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "word_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("language.words.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ease", sa.Float(), nullable=False, server_default="2.5"),
        sa.Column("interval_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("repetitions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("user_id", "word_id", name="uq_language_user_words"),
        schema="language",
    )
    op.create_index(
        "ix_language_user_words_user_due",
        "user_words",
        ["user_id", "due_at"],
        schema="language",
    )


def downgrade() -> None:
    """Drop language tables and schema."""
    op.drop_index(
        "ix_language_user_words_user_due",
        table_name="user_words",
        schema="language",
    )
    op.drop_table("user_words", schema="language")

    op.drop_index(
        "ix_language_words_lang_level",
        table_name="words",
        schema="language",
    )
    op.drop_table("words", schema="language")

    op.execute("DROP SCHEMA IF EXISTS language CASCADE")
