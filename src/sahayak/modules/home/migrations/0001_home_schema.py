"""Create home schema, households, memberships, and invites tables (T9.1).

Revision ID: 0001_home_schema
Revises:
Create Date: 2026-10-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_home_schema"
down_revision = None
branch_labels = None
depends_on = ("0002_users_and_identities",)


def upgrade() -> None:
    """Create home schema and tenancy tables."""
    op.execute("CREATE SCHEMA IF NOT EXISTS home")

    # 1. households table
    op.create_table(
        "households",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("core.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        schema="home",
    )
    op.create_index(
        "ix_home_households_creator",
        "households",
        ["created_by"],
        schema="home",
    )

    # 2. memberships table
    op.create_table(
        "memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "household_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("home.households.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("core.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(32), nullable=False, server_default="member"),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("household_id", "user_id", name="uq_home_membership_household_user"),
        schema="home",
    )
    op.create_index(
        "ix_home_memberships_user",
        "memberships",
        ["user_id"],
        schema="home",
    )
    op.create_index(
        "ix_home_memberships_household",
        "memberships",
        ["household_id"],
        schema="home",
    )

    # 3. invites table
    op.create_table(
        "invites",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "household_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("home.households.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("core.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "used_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("core.users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.UniqueConstraint("code", name="uq_home_invites_code"),
        schema="home",
    )
    op.create_index(
        "ix_home_invites_household",
        "invites",
        ["household_id"],
        schema="home",
    )
    op.create_index(
        "ix_home_invites_code",
        "invites",
        ["code"],
        schema="home",
    )


def downgrade() -> None:
    """Drop home schema tables and schema."""
    op.drop_table("invites", schema="home")
    op.drop_table("memberships", schema="home")
    op.drop_table("households", schema="home")
    op.execute("DROP SCHEMA IF EXISTS home CASCADE")
