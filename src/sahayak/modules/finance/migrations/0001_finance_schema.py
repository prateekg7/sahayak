"""Create finance schema and expenses table (T6.1).

Revision ID: 0001_finance_schema
Revises:
Create Date: 2026-10-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_finance_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create finance schema and expenses table with integer minor units."""
    op.execute("CREATE SCHEMA IF NOT EXISTS finance")

    op.create_table(
        "expenses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("core.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "amount_minor",
            sa.Integer(),
            nullable=False,
            comment="Monetary value in integer minor units (e.g. 20000 for 200.00)",
        ),
        sa.Column(
            "currency",
            sa.String(3),
            nullable=False,
            server_default="INR",
            comment="ISO 4217 3-letter currency code",
        ),
        sa.Column(
            "category",
            sa.String(64),
            nullable=False,
            server_default="other",
        ),
        sa.Column("note", sa.String(255), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        schema="finance",
    )

    op.create_index(
        "ix_finance_expenses_user_occurred",
        "expenses",
        ["user_id", "occurred_at"],
        schema="finance",
    )

    op.create_index(
        "ix_finance_expenses_user_category",
        "expenses",
        ["user_id", "category"],
        schema="finance",
    )


def downgrade() -> None:
    """Drop expenses table and finance schema."""
    op.drop_index(
        "ix_finance_expenses_user_category",
        table_name="expenses",
        schema="finance",
    )
    op.drop_index(
        "ix_finance_expenses_user_occurred",
        table_name="expenses",
        schema="finance",
    )
    op.drop_table("expenses", schema="finance")
    op.execute("DROP SCHEMA IF EXISTS finance CASCADE")
