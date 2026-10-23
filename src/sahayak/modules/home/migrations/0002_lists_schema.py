"""Create lists and list_items tables in home schema (T9.2).

Revision ID: 0002_lists_schema
Revises: 0001_home_schema
Create Date: 2026-10-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_lists_schema"
down_revision = "0001_home_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create lists and list_items tables in home schema."""
    # 1. lists table
    op.create_table(
        "lists",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "household_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("home.households.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(128), nullable=False, server_default="shopping"),
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
        sa.UniqueConstraint("household_id", "name", name="uq_home_lists_household_name"),
        schema="home",
    )
    op.create_index(
        "ix_home_lists_household",
        "lists",
        ["household_id"],
        schema="home",
    )

    # 2. list_items table
    op.create_table(
        "list_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "list_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("home.lists.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("item_name", sa.String(128), nullable=False),
        sa.Column("quantity", sa.String(64), nullable=True),
        sa.Column("checked", sa.Boolean(), nullable=False, server_default=sa.false()),
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
        "ix_home_list_items_list_checked",
        "list_items",
        ["list_id", "checked"],
        schema="home",
    )


def downgrade() -> None:
    """Drop list_items and lists tables from home schema."""
    op.drop_index("ix_home_list_items_list_checked", table_name="list_items", schema="home")
    op.drop_table("list_items", schema="home")
    op.drop_index("ix_home_lists_household", table_name="lists", schema="home")
    op.drop_table("lists", schema="home")
