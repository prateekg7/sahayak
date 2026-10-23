"""Create products table and add product_id to order_items (T10.3).

Revision ID: 0003_products_schema
Revises: 0002_ledger_schema
Create Date: 2026-10-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_products_schema"
down_revision = "0002_ledger_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create products table and add product_id foreign key to order_items."""
    op.create_table(
        "products",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "business_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("business.businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("sku", sa.String(64), nullable=True),
        sa.Column("stock_level", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("low_stock_threshold", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("unit_price_minor", sa.Integer(), nullable=False, server_default="0"),
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
        sa.UniqueConstraint("business_id", "name", name="uq_business_products_business_name"),
        sa.CheckConstraint("stock_level >= 0", name="ck_business_products_stock_non_negative"),
        sa.CheckConstraint(
            "low_stock_threshold >= 0", name="ck_business_products_threshold_non_negative"
        ),
        sa.CheckConstraint("unit_price_minor >= 0", name="ck_business_products_price_non_negative"),
        schema="business",
    )
    op.create_index(
        "ix_business_products_business_stock",
        "products",
        ["business_id", "stock_level"],
        schema="business",
    )

    op.add_column(
        "order_items",
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("business.products.id", ondelete="SET NULL"),
            nullable=True,
        ),
        schema="business",
    )
    op.create_index(
        "ix_business_order_items_product",
        "order_items",
        ["product_id"],
        schema="business",
    )


def downgrade() -> None:
    """Drop products table and product_id column."""
    op.drop_index(
        "ix_business_order_items_product",
        table_name="order_items",
        schema="business",
    )
    op.drop_column("order_items", "product_id", schema="business")
    op.drop_index(
        "ix_business_products_business_stock",
        table_name="products",
        schema="business",
    )
    op.drop_table("products", schema="business")
