"""Create idempotency_keys table in core schema.

Revision ID: 0003_idempotency_keys
Revises: 0002_users_and_identities
Create Date: 2026-10-23
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_idempotency_keys"
down_revision = "0002_users_and_identities"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the idempotency_keys table and unique lookup index."""
    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("tool", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("response", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["core.users.id"],
            name="fk_idempotency_keys_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_idempotency_keys"),
        schema="core",
    )
    op.create_index(
        "ix_core_idempotency_keys_lookup",
        "idempotency_keys",
        ["tool", "key", sa.text("COALESCE(user_id, '00000000-0000-0000-0000-000000000000'::uuid)")],
        unique=True,
        schema="core",
    )


def downgrade() -> None:
    """Drop the idempotency_keys table and index."""
    op.drop_index(
        "ix_core_idempotency_keys_lookup",
        table_name="idempotency_keys",
        schema="core",
    )
    op.drop_table("idempotency_keys", schema="core")
