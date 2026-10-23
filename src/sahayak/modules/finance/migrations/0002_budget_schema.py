"""Create budgets table in finance schema (T6.2).

Revision ID: 0002_budget_schema
Revises: 0001_finance_schema
Create Date: 2026-10-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_budget_schema"
down_revision = "0001_finance_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create budgets table in finance schema."""
    op.create_table(
        "budgets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("core.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "category",
            sa.String(64),
            nullable=False,
            comment="Normalized spending category",
        ),
        sa.Column(
            "amount_minor",
            sa.Integer(),
            nullable=False,
            comment="Monthly budget cap in integer minor units",
        ),
        sa.Column(
            "currency",
            sa.String(3),
            nullable=False,
            server_default="INR",
            comment="ISO 4217 3-letter currency code",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default="true",
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
        sa.UniqueConstraint("user_id", "category", name="uq_finance_budgets_user_category"),
        schema="finance",
    )

    op.create_index(
        "ix_finance_budgets_user_active",
        "budgets",
        ["user_id", "is_active"],
        schema="finance",
    )


def downgrade() -> None:
    """Drop budgets table from finance schema."""
    op.drop_index(
        "ix_finance_budgets_user_active",
        table_name="budgets",
        schema="finance",
    )
    op.drop_table("budgets", schema="finance")
