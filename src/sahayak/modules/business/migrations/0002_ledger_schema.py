"""Create ledger_entries table for customer dues and payments (T10.2).

Revision ID: 0002_ledger_schema
Revises: 0001_business_schema
Create Date: 2026-10-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_ledger_schema"
down_revision = "0001_business_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create ledger_entries table in business schema."""
    op.create_table(
        "ledger_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "business_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("business.businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("business.customers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entry_type", sa.String(32), nullable=False),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("reference_id", sa.String(128), nullable=True),
        sa.Column(
            "reversed_entry_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("business.ledger_entries.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_by",
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
        sa.CheckConstraint("amount_minor > 0", name="ck_business_ledger_amount_positive"),
        schema="business",
    )
    op.create_index(
        "ix_business_ledger_business_customer",
        "ledger_entries",
        ["business_id", "customer_id", "created_at"],
        schema="business",
    )
    op.create_index(
        "ix_business_ledger_customer",
        "ledger_entries",
        ["customer_id", "created_at"],
        schema="business",
    )
    op.create_index(
        "ix_business_ledger_reversed_entry",
        "ledger_entries",
        ["reversed_entry_id"],
        schema="business",
    )


def downgrade() -> None:
    """Drop ledger_entries table."""
    op.drop_index(
        "ix_business_ledger_reversed_entry",
        table_name="ledger_entries",
        schema="business",
    )
    op.drop_index(
        "ix_business_ledger_customer",
        table_name="ledger_entries",
        schema="business",
    )
    op.drop_index(
        "ix_business_ledger_business_customer",
        table_name="ledger_entries",
        schema="business",
    )
    op.drop_table("ledger_entries", schema="business")
