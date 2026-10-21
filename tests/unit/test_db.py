"""Unit tests for transaction ownership."""

from __future__ import annotations

from unittest.mock import AsyncMock, create_autospec

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from sahayak.core.db import UnitOfWork


@pytest.mark.asyncio
async def test_unit_of_work_commits_and_closes_on_success() -> None:
    """A successful operation commits exactly once and releases its session."""
    session = create_autospec(AsyncSession, instance=True)
    session.commit = AsyncMock()
    session.close = AsyncMock()
    session.rollback = AsyncMock()

    async with UnitOfWork(lambda: session) as unit_of_work:
        assert unit_of_work.session is session

    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()
    session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_unit_of_work_rolls_back_and_closes_on_failure() -> None:
    """A failed operation rolls back rather than committing partial changes."""
    session = create_autospec(AsyncSession, instance=True)
    session.commit = AsyncMock()
    session.close = AsyncMock()
    session.rollback = AsyncMock()

    with pytest.raises(RuntimeError, match="boom"):
        async with UnitOfWork(lambda: session):
            raise RuntimeError("boom")

    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()
    session.close.assert_awaited_once()


def test_unit_of_work_rejects_session_access_outside_its_context() -> None:
    """Repositories cannot accidentally use a unit of work before it is active."""
    session = create_autospec(AsyncSession, instance=True)

    with pytest.raises(RuntimeError, match="only inside"):
        _ = UnitOfWork(lambda: session).session
