"""Create business schema, businesses, members, customers, orders, and order_items (T10.1).

Revision ID: 0001_business_schema
Revises:
Create Date: 2026-10-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_business_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create business schema and tables."""
    op.execute("CREATE SCHEMA IF NOT EXISTS business")

    # 1. businesses table
    op.create_table(
        "businesses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("order_seq", sa.Integer(), nullable=False, server_default="0"),
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
        schema="business",
    )
    op.create_index(
        "ix_business_businesses_name",
        "businesses",
        ["name"],
        schema="business",
    )

    # 2. business_members table
    op.create_table(
        "business_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "business_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("business.businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("core.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(32), nullable=False, server_default="owner"),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("business_id", "user_id", name="uq_business_members_business_user"),
        schema="business",
    )
    op.create_index(
        "ix_business_members_user",
        "business_members",
        ["user_id"],
        schema="business",
    )

    # 3. customers table
    op.create_table(
        "customers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "business_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("business.businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        schema="business",
    )
    op.create_index(
        "ix_business_customers_business",
        "customers",
        ["business_id"],
        schema="business",
    )

    # 4. orders table
    op.create_table(
        "orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "business_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("business.businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("order_number", sa.Integer(), nullable=False),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("business.customers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("customer_name", sa.String(128), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("total_amount_minor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("notes", sa.Text(), nullable=True),
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
        sa.UniqueConstraint("business_id", "order_number", name="uq_business_orders_number"),
        schema="business",
    )
    op.create_index(
        "ix_business_orders_business_status",
        "orders",
        ["business_id", "status"],
        schema="business",
    )

    # 5. order_items table
    op.create_table(
        "order_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("business.orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("item_name", sa.String(128), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("unit_price_minor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_price_minor", sa.Integer(), nullable=False, server_default="0"),
        schema="business",
    )
    op.create_index(
        "ix_business_order_items_order",
        "order_items",
        ["order_id"],
        schema="business",
    )


def downgrade() -> None:
    """Drop business tables and schema."""
    op.drop_table("order_items", schema="business")
    op.drop_table("orders", schema="business")
    op.drop_table("customers", schema="business")
    op.drop_table("business_members", schema="business")
    op.drop_table("businesses", schema="business")
    op.execute("DROP SCHEMA IF EXISTS business CASCADE")
