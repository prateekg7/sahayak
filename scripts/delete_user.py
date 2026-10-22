"""Permanently delete user data for GDPR/CCPA privacy compliance (T1.8).

Usage:
    PYTHONPATH=src uv run python scripts/delete_user.py --user-id <UUID> --confirm
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.config import get_settings
from sahayak.core.module import ModuleRegistry
from sahayak.core.privacy import PrivacyCoordinator
from sahayak.shared.users.service import UserService


async def delete_user(user_id: str) -> None:
    """Orchestrate permanent data deletion for the specified user."""
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
        await coordinator.delete_user_data(user_id=user_id)
        print(f"User {user_id} and all associated data permanently erased.")
    finally:
        await engine.dispose()


def main() -> None:
    """CLI entry point for user deletion."""
    parser = argparse.ArgumentParser(description="Permanently erase all data for a user.")
    parser.add_argument("--user-id", required=True, help="UUID of the platform user to erase.")
    parser.add_argument(
        "--confirm",
        action="store_true",
        required=True,
        help="Confirmation flag to prevent accidental deletion.",
    )
    args = parser.parse_args()

    try:
        asyncio.run(delete_user(user_id=args.user_id))
    except Exception as exc:
        print(f"Error deleting user: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
