"""Create feature_flags and user_preferences tables in core schema.

Revision ID: 0006_flags_and_prefs
Revises: 0005_audit_log
Create Date: 2026-10-24
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0006_flags_and_prefs"
down_revision = "0005_audit_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create feature_flags and user_preferences tables in core schema."""
    op.create_table(
        "feature_flags",
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "rollout_percentage", sa.Integer(), nullable=False, server_default=sa.text("100")
        ),
        sa.Column("user_overrides", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("name", name="pk_feature_flags"),
        schema="core",
    )

    op.create_table(
        "user_preferences",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "disabled_modules",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["core.users.id"],
            name="fk_user_preferences_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name="pk_user_preferences"),
        schema="core",
    )


def downgrade() -> None:
    """Drop feature_flags and user_preferences tables."""
    op.drop_table("user_preferences", schema="core")
    op.drop_table("feature_flags", schema="core")
