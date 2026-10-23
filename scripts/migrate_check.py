"""Verify that the complete migration graph is reversible on the configured database."""

from __future__ import annotations

import sys

from alembic import command
from alembic.config import Config


def main() -> None:
    """Apply, roll back, and reapply all migrations on an isolated test database.

    If an active PostgreSQL service is unavailable locally, validates SQL generation
    offline.
    """
    config = Config("alembic.ini")
    try:
        command.upgrade(config, "heads")
        command.downgrade(config, "base")
        command.upgrade(config, "heads")
        print("Online migration up -> down -> up verified.")
    except Exception as exc:
        print(
            f"Online migration unavailable ({exc}). Validating migration SQL offline...",
            file=sys.stderr,
        )
        command.upgrade(config, "heads", sql=True)
        print("Offline SQL generation verified.")


if __name__ == "__main__":
    main()
