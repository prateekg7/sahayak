"""Create users and user_identities tables in core schema.

Revision ID: 0002_users_and_identities
Revises: 0001_core_schema
Create Date: 2026-10-22
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_users_and_identities"
down_revision = "0001_core_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the users and user_identities tables in the core schema."""
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("locale", sa.String(length=32), server_default="en-US", nullable=False),
        sa.Column("timezone", sa.String(length=64), server_default="UTC", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        schema="core",
    )
    op.create_table(
        "user_identities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("issuer", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["core.users.id"],
            name="fk_user_identities_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user_identities"),
        sa.UniqueConstraint("issuer", "subject", name="uq_user_identities_issuer_subject"),
        schema="core",
    )
    op.create_index(
        "ix_core_user_identities_user_id",
        "user_identities",
        ["user_id"],
        unique=False,
        schema="core",
    )


def downgrade() -> None:
    """Drop the user_identities and users tables."""
    op.drop_index(
        "ix_core_user_identities_user_id",
        table_name="user_identities",
        schema="core",
    )
    op.drop_table("user_identities", schema="core")
    op.drop_table("users", schema="core")
