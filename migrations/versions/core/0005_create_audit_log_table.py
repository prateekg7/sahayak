"""Create audit_log table in core schema.

Revision ID: 0005_audit_log
Revises: 0004_outbox_events
Create Date: 2026-10-23
"""

import sqlalchemy as sa
from alembic import op

revision = "0005_audit_log"
down_revision = "0004_outbox_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create audit_log table with non-sensitive audit metadata."""
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("resource", sa.String(length=128), nullable=False),
        sa.Column("ip_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["core.users.id"],
            name="fk_audit_log_user_id_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_log"),
        schema="core",
    )
    op.create_index(
        "ix_core_audit_log_user_id",
        "audit_log",
        ["user_id", "created_at"],
        schema="core",
    )
    op.create_index(
        "ix_core_audit_log_action",
        "audit_log",
        ["action", "created_at"],
        schema="core",
    )
    op.create_index(
        "ix_core_audit_log_created_at",
        "audit_log",
        ["created_at"],
        schema="core",
    )


def downgrade() -> None:
    """Drop audit_log table and its indexes."""
    op.drop_index("ix_core_audit_log_created_at", table_name="audit_log", schema="core")
    op.drop_index("ix_core_audit_log_action", table_name="audit_log", schema="core")
    op.drop_index("ix_core_audit_log_user_id", table_name="audit_log", schema="core")
    op.drop_table("audit_log", schema="core")
