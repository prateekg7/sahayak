"""Create chores, pantry_items, and household_preferences tables in home schema (T9.3).

Revision ID: 0003_chores_and_pantry_schema
Revises: 0002_lists_schema
Create Date: 2026-10-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_chores_and_pantry_schema"
down_revision = "0002_lists_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create chores, pantry_items, and household_preferences tables."""
    # 1. chores table
    op.create_table(
        "chores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "household_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("home.households.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column(
            "assigned_to",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("core.users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "rotation_members",
            postgresql.JSONB,
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "rotation_index",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "frequency",
            sa.String(32),
            nullable=False,
            server_default="weekly",
        ),
        sa.Column("last_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_completed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("core.users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("next_due_at", sa.DateTime(timezone=True), nullable=True),
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
        schema="home",
    )
    op.create_index(
        "ix_home_chores_household",
        "chores",
        ["household_id"],
        schema="home",
    )

    # 2. pantry_items table
    op.create_table(
        "pantry_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "household_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("home.households.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("item_name", sa.String(128), nullable=False),
        sa.Column("quantity", sa.String(64), nullable=True),
        sa.Column("expires_at", sa.Date(), nullable=True),
        sa.Column(
            "added_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("core.users.id", ondelete="SET NULL"),
            nullable=True,
        ),
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
        schema="home",
    )
    op.create_index(
        "ix_home_pantry_household",
        "pantry_items",
        ["household_id"],
        schema="home",
    )

    # 3. household_preferences table
    op.create_table(
        "household_preferences",
        sa.Column(
            "household_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("home.households.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("diet", sa.String(64), nullable=False, server_default="any"),
        sa.Column(
            "allergies",
            postgresql.JSONB,
            nullable=False,
            server_default="[]",
        ),
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
        schema="home",
    )


def downgrade() -> None:
    """Drop household_preferences, pantry_items, and chores tables."""
    op.drop_table("household_preferences", schema="home")
    op.drop_index("ix_home_pantry_household", table_name="pantry_items", schema="home")
    op.drop_table("pantry_items", schema="home")
    op.drop_index("ix_home_chores_household", table_name="chores", schema="home")
    op.drop_table("chores", schema="home")
