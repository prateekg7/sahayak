"""Create academics schema and tables for quizzes, flashcards, study plans, and stats.

Revision ID: 0001_academics_schema
Revises:
Create Date: 2026-10-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_academics_schema"
down_revision = None
branch_labels = ("academics",)
depends_on = ("0002_users_and_identities",)


def upgrade() -> None:
    """Create academics schema, enum types, tables, and indexes."""
    op.execute("CREATE SCHEMA IF NOT EXISTS academics")

    # PostgreSQL enum types in academics schema
    difficulty_enum = postgresql.ENUM(
        "easy", "medium", "hard", name="difficulty_level", schema="academics"
    )
    difficulty_enum.create(op.get_bind(), checkfirst=True)

    question_status_enum = postgresql.ENUM(
        "approved", "flagged", "quarantined", name="question_status", schema="academics"
    )
    question_status_enum.create(op.get_bind(), checkfirst=True)

    quiz_status_enum = postgresql.ENUM(
        "in_progress", "completed", "abandoned", "expired", name="quiz_status", schema="academics"
    )
    quiz_status_enum.create(op.get_bind(), checkfirst=True)

    # 1. topics
    op.create_table(
        "topics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("topic_key", sa.String(length=128), nullable=False, unique=True),
        sa.Column("display_name", sa.String(length=256), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        schema="academics",
    )

    # 2. questions
    op.create_table(
        "questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "topic_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("academics.topics.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "difficulty",
            postgresql.ENUM(
                "easy",
                "medium",
                "hard",
                name="difficulty_level",
                schema="academics",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("stem", sa.Text(), nullable=False),
        sa.Column("options", postgresql.JSONB(), nullable=False),
        sa.Column("correct_key", sa.String(length=1), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("source_url", sa.String(length=1024), nullable=True),
        sa.Column("source_hash", sa.String(length=64), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("prompt_version", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "approved",
                "flagged",
                "quarantined",
                name="question_status",
                schema="academics",
                create_type=False,
            ),
            server_default="approved",
            nullable=False,
        ),
        sa.Column("flag_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        schema="academics",
    )
    op.create_index(
        "ix_academics_questions_lookup",
        "questions",
        ["topic_id", "difficulty", "status"],
        schema="academics",
    )

    # 3. quizzes
    op.create_table(
        "quizzes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("core.users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "topic_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("academics.topics.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "difficulty",
            postgresql.ENUM(
                "easy",
                "medium",
                "hard",
                name="difficulty_level",
                schema="academics",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("current_index", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "in_progress",
                "completed",
                "abandoned",
                "expired",
                name="quiz_status",
                schema="academics",
                create_type=False,
            ),
            server_default="in_progress",
            nullable=False,
        ),
        sa.Column("score_correct", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        schema="academics",
    )
    op.create_index(
        "ix_academics_quizzes_user_status",
        "quizzes",
        ["user_id", "status"],
        schema="academics",
    )

    # 4. quiz_questions
    op.create_table(
        "quiz_questions",
        sa.Column(
            "quiz_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("academics.quizzes.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("position", sa.Integer(), primary_key=True),
        sa.Column(
            "question_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("academics.questions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("selected_key", sa.String(length=1), nullable=True),
        sa.Column("is_correct", sa.Boolean(), nullable=True),
        schema="academics",
    )

    # 5. decks
    op.create_table(
        "decks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("core.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", "name", name="uq_academics_decks_user_name"),
        schema="academics",
    )

    # 6. cards
    op.create_table(
        "cards",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "deck_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("academics.decks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("core.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("front", sa.Text(), nullable=False),
        sa.Column("back", sa.Text(), nullable=False),
        sa.Column("ease", sa.Float(), server_default="2.5", nullable=False),
        sa.Column("interval_days", sa.Integer(), server_default="0", nullable=False),
        sa.Column("repetitions", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "due_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        schema="academics",
    )
    op.create_index(
        "ix_academics_cards_user_due",
        "cards",
        ["user_id", "due_at"],
        schema="academics",
    )

    # 7. study_plans
    op.create_table(
        "study_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("core.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("goal", sa.String(length=256), nullable=False),
        sa.Column("exam_date", sa.Date(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        schema="academics",
    )
    op.create_index(
        "ix_academics_plans_user",
        "study_plans",
        ["user_id"],
        schema="academics",
    )

    # 8. plan_tasks
    op.create_table(
        "plan_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("academics.study_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("topic", sa.String(length=256), nullable=False),
        sa.Column("minutes", sa.Integer(), nullable=False),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        schema="academics",
    )
    op.create_index(
        "ix_academics_plan_tasks_plan_date",
        "plan_tasks",
        ["plan_id", "date"],
        schema="academics",
    )

    # 9. topic_stats
    op.create_table(
        "topic_stats",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("core.users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "topic_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("academics.topics.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("correct", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "last_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        schema="academics",
    )


def downgrade() -> None:
    """Drop all tables in academics schema, followed by enum types and schema."""
    op.drop_table("topic_stats", schema="academics")
    op.drop_index("ix_academics_plan_tasks_plan_date", table_name="plan_tasks", schema="academics")
    op.drop_table("plan_tasks", schema="academics")
    op.drop_index("ix_academics_plans_user", table_name="study_plans", schema="academics")
    op.drop_table("study_plans", schema="academics")
    op.drop_index("ix_academics_cards_user_due", table_name="cards", schema="academics")
    op.drop_table("cards", schema="academics")
    op.drop_table("decks", schema="academics")
    op.drop_table("quiz_questions", schema="academics")
    op.drop_index("ix_academics_quizzes_user_status", table_name="quizzes", schema="academics")
    op.drop_table("quizzes", schema="academics")
    op.drop_index("ix_academics_questions_lookup", table_name="questions", schema="academics")
    op.drop_table("questions", schema="academics")
    op.drop_table("topics", schema="academics")

    # Drop enum types
    op.execute("DROP TYPE IF EXISTS academics.quiz_status")
    op.execute("DROP TYPE IF EXISTS academics.question_status")
    op.execute("DROP TYPE IF EXISTS academics.difficulty_level")

    # Drop schema
    op.execute("DROP SCHEMA IF EXISTS academics CASCADE")
