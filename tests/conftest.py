"""Pytest configuration and session fixtures."""

from __future__ import annotations

import asyncio
import logging

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from sahayak.core.config import get_settings

logger = logging.getLogger(__name__)


@pytest.fixture(scope="session", autouse=True)
def prepare_test_database() -> None:
    """Run Alembic migrations to head if a PostgreSQL database is reachable."""
    settings = get_settings()

    async def _check_db() -> bool:
        try:
            engine = create_async_engine(str(settings.database_url))
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            await engine.dispose()
            return True
        except Exception:
            return False

    is_db_up = asyncio.run(_check_db())
    if is_db_up:
        config = Config("alembic.ini")
        command.upgrade(config, "head")
