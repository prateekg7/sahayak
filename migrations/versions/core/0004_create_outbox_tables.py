"""Create outbox_events and dead_letter_events tables in core schema.

Revision ID: 0004_outbox_events
Revises: 0003_idempotency_keys
Create Date: 2026-10-23
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_outbox_events"
down_revision = "0003_idempotency_keys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the outbox_events and dead_letter_events tables."""
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("aggregate", sa.String(length=128), nullable=False),
        sa.Column("type", sa.String(length=128), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_outbox_events"),
        schema="core",
    )
    op.create_index(
        "ix_core_outbox_events_unprocessed",
        "outbox_events",
        ["created_at"],
        postgresql_where=sa.text("processed_at IS NULL"),
        schema="core",
    )

    op.create_table(
        "dead_letter_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("outbox_event_id", sa.Uuid(), nullable=False),
        sa.Column("aggregate", sa.String(length=128), nullable=False),
        sa.Column("type", sa.String(length=128), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column(
            "failed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_dead_letter_events"),
        schema="core",
    )


def downgrade() -> None:
    """Drop outbox_events and dead_letter_events tables."""
    op.drop_table("dead_letter_events", schema="core")
    op.drop_index(
        "ix_core_outbox_events_unprocessed",
        table_name="outbox_events",
        schema="core",
    )
    op.drop_table("outbox_events", schema="core")
