"""Export all user data for GDPR/CCPA privacy compliance (T1.8).

Usage:
    PYTHONPATH=src uv run python scripts/export_user.py --user-id <UUID> [--output data.json]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.config import get_settings
from sahayak.core.module import ModuleRegistry
from sahayak.core.privacy import PrivacyCoordinator
from sahayak.shared.users.service import UserService


async def export_user(user_id: str, output_path: str | None = None) -> None:
    """Orchestrate full data export for the specified user."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    registry = ModuleRegistry()
    registry.load(settings.enabled_modules)

    user_service = UserService(session_factory=session_factory)
    coordinator = PrivacyCoordinator(
        session_factory=session_factory,
        user_service=user_service,
        registry=registry,
    )

    try:
        data = await coordinator.export_user_data(user_id=user_id)
        formatted = json.dumps(data, indent=2, sort_keys=True)
        if output_path:
            Path(output_path).write_text(formatted, encoding="utf-8")
            print(f"User data exported successfully to {output_path}")
        else:
            print(formatted)
    finally:
        await engine.dispose()


def main() -> None:
    """CLI entry point for user export."""
    parser = argparse.ArgumentParser(description="Export all platform data for a user.")
    parser.add_argument("--user-id", required=True, help="UUID of the platform user to export.")
    parser.add_argument("--output", required=False, help="Optional output JSON filepath.")
    args = parser.parse_args()

    try:
        asyncio.run(export_user(user_id=args.user_id, output_path=args.output))
    except Exception as exc:
        print(f"Error exporting user: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
