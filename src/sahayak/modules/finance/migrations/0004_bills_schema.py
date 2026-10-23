"""Create bills table in finance schema (T6.4).

Revision ID: 0004_bills_schema
Revises: 0003_split_bill_schema
Create Date: 2026-10-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_bills_schema"
down_revision = "0003_split_bill_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create bills table for recurring due dates and EMIs."""
    op.create_table(
        "bills",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("core.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column(
            "amount_minor",
            sa.Integer(),
            nullable=False,
            comment="Due amount in integer minor units",
        ),
        sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("frequency", sa.String(32), nullable=False, server_default="monthly"),
        sa.Column("due_day", sa.Integer(), nullable=False),
        sa.Column("next_due_date", sa.Date(), nullable=False),
        sa.Column("is_paid", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        schema="finance",
    )

    op.create_index(
        "ix_finance_bills_user_due",
        "bills",
        ["user_id", "next_due_date"],
        schema="finance",
    )


def downgrade() -> None:
    """Drop bills table from finance schema."""
    op.drop_index("ix_finance_bills_user_due", table_name="bills", schema="finance")
    op.drop_table("bills", schema="finance")
