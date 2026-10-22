"""Integration tests for privacy export, erasure, and retention on PostgreSQL (T1.8)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.audit import AuditLogger, AuditLogRecord
from sahayak.core.config import get_settings
from sahayak.core.db.session import UnitOfWork
from sahayak.core.idempotency import IdempotencyRecord
from sahayak.core.module import ModuleRegistry
from sahayak.core.privacy import PrivacyCoordinator, RetentionManager
from sahayak.shared.users.models import User, UserIdentity
from sahayak.shared.users.service import UserService


@pytest.mark.integration
@pytest.mark.asyncio
async def test_privacy_export_and_complete_erasure_on_postgres() -> None:
    """Full lifecycle: export collects all data, and erasure leaves no referencing rows."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("PostgreSQL database is not accessible")

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    user_service = UserService(session_factory=session_factory)
    audit_logger = AuditLogger()

    registry = ModuleRegistry()
    registry.load(("_template",))

    coordinator = PrivacyCoordinator(
        session_factory=session_factory,
        user_service=user_service,
        registry=registry,
        audit_logger=audit_logger,
    )

    test_sub = f"privacy-sub-{uuid.uuid4()}"
    user = await user_service.get_or_create_by_identity(
        issuer="https://auth.example.com",
        subject=test_sub,
        locale="en-US",
        timezone="UTC",
    )
    user_id = user.id

    # Add an idempotency key for this user
    async with UnitOfWork(session_factory) as uow:
        idemp = IdempotencyRecord(
            id=uuid.uuid4(),
            key="req-priv-1",
            tool="ping_echo",
            user_id=user_id,
            response={"ok": True},
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        uow.session.add(idemp)
        await audit_logger.log(
            uow.session,
            action="tool.execute",
            resource="ping_echo",
            user_id=user_id,
            client_ip="192.168.1.1",
        )
        await uow.session.commit()

    # 1. Export user data
    bundle = await coordinator.export_user_data(user_id=user_id, client_ip="192.168.1.1")
    assert bundle["user_id"] == str(user_id)
    assert len(bundle["identities"]) == 1
    assert bundle["identities"][0]["subject"] == test_sub
    assert "_template" in bundle["modules"]
    assert any(a["action"] == "tool.execute" for a in bundle["audit_trail"])

    # 2. Delete user data (Right to be Forgotten)
    await coordinator.delete_user_data(user_id=user_id, client_ip="192.168.1.1")

    # 3. Verify complete erasure across all tables
    async with UnitOfWork(session_factory) as uow:
        # Check users table
        u_res = await uow.session.execute(select(User).where(User.id == user_id))
        assert u_res.scalar_one_or_none() is None

        # Check user_identities table
        ident_res = await uow.session.execute(
            select(UserIdentity).where(UserIdentity.user_id == user_id)
        )
        assert len(ident_res.scalars().all()) == 0

        # Check idempotency_keys table
        idemp_res = await uow.session.execute(
            select(IdempotencyRecord).where(IdempotencyRecord.user_id == user_id)
        )
        assert len(idemp_res.scalars().all()) == 0

        # Check audit_log: any previous records must have user_id anonymized to NULL
        audit_res = await uow.session.execute(
            select(AuditLogRecord).where(AuditLogRecord.user_id == user_id)
        )
        assert len(audit_res.scalars().all()) == 0

        # Check that an anonymized user.delete audit event exists with user_id == None
        del_event = (
            await uow.session.execute(
                select(AuditLogRecord).where(
                    AuditLogRecord.action == "user.delete",
                    AuditLogRecord.resource == f"user:{user_id}",
                )
            )
        ).scalar_one_or_none()
        assert del_event is not None
        assert del_event.user_id is None

    await engine.dispose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_retention_manager_pruning_on_postgres() -> None:
    """Retention cleanup purges expired idempotency keys and stale audit logs."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("PostgreSQL database is not accessible")

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    retention = RetentionManager(session_factory=session_factory)

    # Seed an expired idempotency record and an old audit log record
    old_time = datetime.now(UTC) - timedelta(days=120)
    async with UnitOfWork(session_factory) as uow:
        expired_idemp = IdempotencyRecord(
            id=uuid.uuid4(),
            key=f"exp-{uuid.uuid4()}",
            tool="ping_echo",
            user_id=None,
            response={"ok": True},
            expires_at=datetime.now(UTC) - timedelta(minutes=5),
        )
        old_audit = AuditLogRecord(
            id=uuid.uuid4(),
            user_id=None,
            action="system.test",
            resource="test",
            created_at=old_time,
        )
        uow.session.add(expired_idemp)
        uow.session.add(old_audit)
        await uow.session.commit()

    # Run cleanup with 90 day threshold
    counts = await retention.run_cleanup(audit_days=90)
    assert counts["pruned_idempotency_keys"] >= 1
    assert counts["pruned_audit_logs"] >= 1

    await engine.dispose()
