"""Create groups, group_members, shared_expenses, settlements tables (T6.3).

Revision ID: 0003_split_bill_schema
Revises: 0002_budget_schema
Create Date: 2026-10-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_split_bill_schema"
down_revision = "0002_budget_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create bill splitting schema tables."""
    # 1. groups
    op.create_table(
        "groups",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("core.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        schema="finance",
    )
    op.create_index(
        "ix_finance_groups_user_id",
        "groups",
        ["user_id"],
        schema="finance",
    )

    # 2. group_members
    op.create_table(
        "group_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "group_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("finance.groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("group_id", "name", name="uq_finance_group_members_group_name"),
        schema="finance",
    )

    # 3. shared_expenses
    op.create_table(
        "shared_expenses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "group_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("finance.groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("payer_name", sa.String(64), nullable=False),
        sa.Column("total_minor", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("split_data", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        schema="finance",
    )
    op.create_index(
        "ix_finance_shared_expenses_group",
        "shared_expenses",
        ["group_id"],
        schema="finance",
    )

    # 4. settlements
    op.create_table(
        "settlements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "group_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("finance.groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("from_name", sa.String(64), nullable=False),
        sa.Column("to_name", sa.String(64), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column(
            "settled_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        schema="finance",
    )
    op.create_index(
        "ix_finance_settlements_group",
        "settlements",
        ["group_id"],
        schema="finance",
    )


def downgrade() -> None:
    """Drop bill splitting tables in reverse order."""
    op.drop_index("ix_finance_settlements_group", table_name="settlements", schema="finance")
    op.drop_table("settlements", schema="finance")

    op.drop_index(
        "ix_finance_shared_expenses_group", table_name="shared_expenses", schema="finance"
    )
    op.drop_table("shared_expenses", schema="finance")

    op.drop_table("group_members", schema="finance")

    op.drop_index("ix_finance_groups_user_id", table_name="groups", schema="finance")
    op.drop_table("groups", schema="finance")
