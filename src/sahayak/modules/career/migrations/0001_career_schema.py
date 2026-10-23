"""Create career schema and interview practice tables (T8.1).

Revision ID: 0001_career_schema
Revises:
Create Date: 2026-10-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_career_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create career schema, interview_sessions, and interview_turns tables."""
    op.execute("CREATE SCHEMA IF NOT EXISTS career")

    op.create_table(
        "interview_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("core.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(128), nullable=False),
        sa.Column("level", sa.String(32), nullable=False, server_default="mid"),
        sa.Column("status", sa.String(32), nullable=False, server_default="in_progress"),
        sa.Column("total_questions", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("current_question_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "questions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        schema="career",
    )

    op.create_index(
        "ix_career_sessions_user_status",
        "interview_sessions",
        ["user_id", "status"],
        schema="career",
    )

    op.create_table(
        "interview_turns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("career.interview_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("question_index", sa.Integer(), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("user_answer", sa.Text(), nullable=False),
        sa.Column("clarity_score", sa.Integer(), nullable=False),
        sa.Column("relevance_score", sa.Integer(), nullable=False),
        sa.Column("depth_score", sa.Integer(), nullable=False),
        sa.Column(
            "feedback_tips",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("feedback_spoken", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.String(32), nullable=False, server_default="v1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("session_id", "question_index", name="uq_career_turns_session_q_idx"),
        schema="career",
    )

    op.create_index(
        "ix_career_turns_session",
        "interview_turns",
        ["session_id"],
        schema="career",
    )


def downgrade() -> None:
    """Drop career tables and schema."""
    op.drop_index("ix_career_turns_session", table_name="interview_turns", schema="career")
    op.drop_table("interview_turns", schema="career")
    op.drop_index(
        "ix_career_sessions_user_status", table_name="interview_sessions", schema="career"
    )
    op.drop_table("interview_sessions", schema="career")
    op.execute("DROP SCHEMA IF EXISTS career CASCADE")
