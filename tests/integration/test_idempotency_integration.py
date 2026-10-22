"""Integration tests for idempotency table and service on PostgreSQL (T1.5)."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.config import get_settings
from sahayak.core.db.session import UnitOfWork
from sahayak.core.idempotency import IdempotencyRecord, IdempotencyRepository, IdempotencyService
from sahayak.shared.users.service import UserService


@pytest.mark.integration
@pytest.mark.asyncio
async def test_idempotency_persistence_and_concurrency_on_postgres() -> None:
    """Store, retrieve, and concurrent execution handling on PostgreSQL."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("PostgreSQL database is not accessible")

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    user_service = UserService(session_factory=session_factory)
    test_user = await user_service.get_or_create_by_identity(
        issuer="https://auth.example.com",
        subject=f"idemp-test-{uuid.uuid4()}",
    )

    repo = IdempotencyRepository()
    service = IdempotencyService(session_factory=session_factory, repo=repo)

    tool_name = "test_mutation"
    req_key = f"req-{uuid.uuid4()}"
    test_resp = {"ok": True, "spoken_summary": "Executed once", "data": {"val": 42}}

    # 1. Store response
    stored = await service.store(
        tool=tool_name,
        key=req_key,
        user_id=test_user.id,
        response=test_resp,
        ttl_seconds=3600,
    )
    assert stored == test_resp

    # 2. Retrieve response
    retrieved = await service.get(tool=tool_name, key=req_key, user_id=test_user.id)
    assert retrieved == test_resp

    # 3. Concurrent store for the same key handles race condition cleanly
    concurrent_key = f"req-race-{uuid.uuid4()}"
    results = await asyncio.gather(
        *(
            service.store(
                tool=tool_name,
                key=concurrent_key,
                user_id=test_user.id,
                response={"ok": True, "worker": i},
                ttl_seconds=3600,
            )
            for i in range(5)
        )
    )
    # All workers should get a valid response without crashing
    assert len(results) == 5
    assert all(r["ok"] is True for r in results)

    # 4. Expired record is ignored
    expired_key = f"req-exp-{uuid.uuid4()}"
    async with UnitOfWork(session_factory) as uow:
        expired_record = IdempotencyRecord(
            id=uuid.uuid4(),
            tool=tool_name,
            key=expired_key,
            user_id=test_user.id,
            response={"ok": True, "old": True},
            expires_at=datetime.now(UTC) - timedelta(seconds=10),
        )
        uow.session.add(expired_record)

    expired_retrieved = await service.get(tool=tool_name, key=expired_key, user_id=test_user.id)
    assert expired_retrieved is None

    # Cleanup test user
    await user_service.soft_delete_user(test_user.id)
    await engine.dispose()
