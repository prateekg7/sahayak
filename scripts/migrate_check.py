"""Verify that the complete migration graph is reversible on the configured database."""

from __future__ import annotations

from alembic import command
from alembic.config import Config


def main() -> None:
    """Apply, roll back, and reapply all migrations on an isolated test database."""
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")


if __name__ == "__main__":
    main()
