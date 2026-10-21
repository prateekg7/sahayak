"""Create the schema owned by core infrastructure.

Revision ID: 0001_core_schema
Revises:
Create Date: 2026-10-22
"""

from alembic import op

revision = "0001_core_schema"
down_revision = None
branch_labels = ("core",)
depends_on = None


def upgrade() -> None:
    """Create the core schema without affecting module-owned schemas."""
    op.execute("CREATE SCHEMA core")


def downgrade() -> None:
    """Remove the empty core schema created by this migration."""
    op.execute("DROP SCHEMA core")
