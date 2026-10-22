"""Unit tests for privacy, audit logging, and data export (T1.8)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from sahayak.core.audit import AuditLogger
from sahayak.core.errors import NotFoundError
from sahayak.core.module import ModuleRegistry
from sahayak.core.privacy import PrivacyCoordinator
from sahayak.shared.users.models import User, UserIdentity


@pytest.mark.asyncio
async def test_audit_logger_hashes_ip_address() -> None:
    """Client IP addresses are hashed using SHA-256 for privacy."""
    logger = AuditLogger()
    raw_ip = "192.168.1.100"
    ip_hash = logger.hash_ip(raw_ip)

    assert ip_hash is not None
    assert raw_ip not in ip_hash
    assert len(ip_hash) == 64
    assert ip_hash == logger.hash_ip(raw_ip)  # Deterministic
    assert logger.hash_ip(None) is None


@pytest.mark.asyncio
async def test_export_user_data_structure() -> None:
    """Export produces standardized JSON bundle aggregating user and module records."""
    user_id = uuid.uuid4()
    now = datetime.now(UTC)
    mock_user = User(id=user_id, locale="en-US", timezone="Asia/Kolkata", created_at=now)
    mock_identity = UserIdentity(
        id=uuid.uuid4(),
        user_id=user_id,
        issuer="https://auth.example.com",
        subject="test-sub",
        created_at=now,
    )

    user_service = MagicMock()
    user_service.get_by_id = AsyncMock(return_value=mock_user)
    user_service.get_identities = AsyncMock(return_value=[mock_identity])

    mock_module = MagicMock()
    mock_module.name = "sample_mod"
    mock_module.export_user_data = MagicMock(return_value={"records": [{"id": 1}]})

    registry = ModuleRegistry()
    registry.register(mock_module)

    session_factory = MagicMock()
    # Mock UnitOfWork context manager
    uow_mock = AsyncMock()
    session_factory.return_value = uow_mock
    uow_mock.__aenter__.return_value = uow_mock
    uow_mock.session = AsyncMock()
    empty_result = MagicMock(scalars=lambda: MagicMock(all=lambda: []))
    uow_mock.session.execute = AsyncMock(return_value=empty_result)

    audit_mock = MagicMock()
    audit_mock.list_for_user = AsyncMock(return_value=[])
    audit_mock.log = AsyncMock()

    coordinator = PrivacyCoordinator(
        session_factory=session_factory,
        user_service=user_service,
        registry=registry,
        audit_logger=audit_mock,
    )

    bundle = await coordinator.export_user_data(user_id=user_id, client_ip="10.0.0.1")

    assert bundle["user_id"] == str(user_id)
    assert bundle["profile"]["locale"] == "en-US"
    assert bundle["profile"]["timezone"] == "Asia/Kolkata"
    assert len(bundle["identities"]) == 1
    assert bundle["identities"][0]["subject"] == "test-sub"
    assert bundle["modules"]["sample_mod"]["records"][0]["id"] == 1

    # Verify audit log was recorded
    audit_mock.log.assert_called_once()
    assert audit_mock.log.call_args[1]["action"] == "user.export"


@pytest.mark.asyncio
async def test_export_nonexistent_user_raises_not_found() -> None:
    """Requesting export for unknown user raises NotFoundError."""
    user_service = MagicMock()
    user_service.get_by_id = AsyncMock(return_value=None)

    coordinator = PrivacyCoordinator(
        session_factory=MagicMock(),
        user_service=user_service,
    )

    with pytest.raises(NotFoundError):
        await coordinator.export_user_data(user_id=uuid.uuid4())
