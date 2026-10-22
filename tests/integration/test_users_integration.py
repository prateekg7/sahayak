"""Integration tests for platform user provisioning on real PostgreSQL."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.config import get_settings
from sahayak.shared.users.service import UserService


@pytest.mark.integration
@pytest.mark.asyncio
async def test_concurrent_user_provisioning_is_idempotent() -> None:
    """Concurrent first-requests for the same identity yield exactly one user."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("PostgreSQL database is not accessible")

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    service = UserService(session_factory=session_factory)

    test_sub = f"sub-concurrent-{uuid.uuid4()}"
    issuer = "https://auth.example.com"

    # Spawn 10 concurrent provisioning requests for the exact same identity
    results = await asyncio.gather(
        *(
            service.get_or_create_by_identity(
                issuer=issuer,
                subject=test_sub,
                locale="en-US",
                timezone="UTC",
            )
            for _ in range(10)
        )
    )

    # All 10 returned users must share the exact same user_id
    first_user_id = results[0].id
    assert all(u.id == first_user_id for u in results)

    # Clean up test user
    await service.soft_delete_user(first_user_id)
    deleted_check = await service.get_by_id(first_user_id)
    assert deleted_check is None

    await engine.dispose()
