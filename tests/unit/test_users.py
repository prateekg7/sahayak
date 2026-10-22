"""Unit tests for platform user model, repository, and service."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from sahayak.shared.users.models import User, UserIdentity
from sahayak.shared.users.repo import UserRepository
from sahayak.shared.users.service import UserService


def test_user_and_identity_model_instantiation() -> None:
    """User and identity models can be constructed with defaults."""
    user = User(locale="en-US", timezone="UTC")
    assert user.id is not None
    assert user.locale == "en-US"
    assert user.timezone == "UTC"
    assert user.deleted_at is None

    identity = UserIdentity(
        user_id=user.id,
        issuer="https://auth.example.com",
        subject="sub-123",
    )
    assert identity.id is not None
    assert identity.user_id == user.id
    assert identity.issuer == "https://auth.example.com"
    assert identity.subject == "sub-123"


@pytest.mark.asyncio
async def test_user_service_get_by_id() -> None:
    """UserService fetches user by UUID via repository."""
    session = AsyncMock(spec=AsyncSession)
    user_id = uuid.uuid4()
    expected_user = User(id=user_id, locale="en-US", timezone="UTC")

    repo = AsyncMock(spec=UserRepository)
    repo.get_by_id = AsyncMock(return_value=expected_user)

    service = UserService(session_factory=lambda: session, repo=repo)
    result = await service.get_by_id(user_id)

    assert result is expected_user
    repo.get_by_id.assert_awaited_once_with(session, user_id)


@pytest.mark.asyncio
async def test_user_service_get_or_create_returns_existing() -> None:
    """UserService returns existing user if identity already exists."""
    session = AsyncMock(spec=AsyncSession)
    existing_user = User(locale="en-US", timezone="UTC")

    repo = AsyncMock(spec=UserRepository)
    repo.get_by_identity = AsyncMock(return_value=existing_user)

    service = UserService(session_factory=lambda: session, repo=repo)
    result = await service.get_or_create_by_identity("https://auth.example.com", "sub-123")

    assert result is existing_user
    repo.get_by_identity.assert_awaited_once_with(session, "https://auth.example.com", "sub-123")
    assert not repo.create_user_with_identity.called


@pytest.mark.asyncio
async def test_user_service_get_or_create_provisions_new() -> None:
    """UserService provisions new user when identity does not exist."""
    session = AsyncMock(spec=AsyncSession)
    new_user = User(locale="en-IN", timezone="Asia/Kolkata")

    repo = AsyncMock(spec=UserRepository)
    repo.get_by_identity = AsyncMock(return_value=None)
    repo.create_user_with_identity = AsyncMock(return_value=new_user)

    service = UserService(session_factory=lambda: session, repo=repo)
    result = await service.get_or_create_by_identity(
        "https://auth.example.com",
        "sub-456",
        locale="en-IN",
        timezone="Asia/Kolkata",
    )

    assert result is new_user
    repo.create_user_with_identity.assert_awaited_once_with(
        session,
        issuer="https://auth.example.com",
        subject="sub-456",
        locale="en-IN",
        timezone="Asia/Kolkata",
    )


@pytest.mark.asyncio
async def test_user_service_recovers_from_concurrent_insert_race() -> None:
    """UserService catches IntegrityError during savepoint and returns winner's user."""
    session = AsyncMock(spec=AsyncSession)
    winner_user = User(locale="en-US", timezone="UTC")

    repo = AsyncMock(spec=UserRepository)
    # First check: returns None
    # After IntegrityError: returns winner_user
    repo.get_by_identity = AsyncMock(side_effect=[None, winner_user])
    repo.create_user_with_identity = AsyncMock(
        side_effect=IntegrityError("statement", {}, Exception("unique constraint violation"))
    )

    service = UserService(session_factory=lambda: session, repo=repo)
    result = await service.get_or_create_by_identity("https://auth.example.com", "sub-race")

    assert result is winner_user
    assert repo.get_by_identity.await_count == 2
    repo.create_user_with_identity.assert_awaited_once()


@pytest.mark.asyncio
async def test_user_service_soft_delete() -> None:
    """UserService soft-deletes an active user."""
    session = AsyncMock(spec=AsyncSession)
    user_id = uuid.uuid4()

    repo = AsyncMock(spec=UserRepository)
    repo.soft_delete_user = AsyncMock(return_value=True)

    service = UserService(session_factory=lambda: session, repo=repo)
    result = await service.soft_delete_user(user_id)

    assert result is True
    repo.soft_delete_user.assert_awaited_once_with(session, user_id)
