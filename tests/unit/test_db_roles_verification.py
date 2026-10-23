"""Unit tests for the database roles verification script (T4.1)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from scripts.verify_app_db_role import (
    DDLPermissionViolationError,
    verify_app_role_cannot_run_ddl,
)
from sqlalchemy.exc import ProgrammingError


@pytest.mark.asyncio
async def test_verify_app_role_passes_when_ddl_fails() -> None:
    """When DDL triggers a ProgrammingError (permission denied), verification passes."""
    session = AsyncMock()

    # DML succeeds
    mock_dml_result = MagicMock()
    mock_dml_result.scalar.return_value = 1

    # DDL raises permission denied
    permission_denied = ProgrammingError(
        statement="CREATE TABLE ...",
        params={},
        orig=Exception("permission denied for schema core"),
    )

    session.execute.side_effect = [
        mock_dml_result,  # SELECT 1
        permission_denied,  # CREATE TABLE
        permission_denied,  # DROP TABLE
    ]

    summary = await verify_app_role_cannot_run_ddl(session)
    assert summary["status"] == "passed"
    assert summary["dml_allowed"] == "true"
    assert summary["ddl_create_blocked"] == "true"
    assert summary["ddl_drop_blocked"] == "true"


@pytest.mark.asyncio
async def test_verify_app_role_fails_when_ddl_create_succeeds() -> None:
    """If CREATE TABLE unexpectedly succeeds, DDLPermissionViolationError is raised."""
    session = AsyncMock()

    mock_dml_result = MagicMock()
    mock_dml_result.scalar.return_value = 1

    session.execute.side_effect = [
        mock_dml_result,  # SELECT 1
        MagicMock(),  # CREATE TABLE succeeds!
    ]

    with pytest.raises(DDLPermissionViolationError, match="CREATE TABLE in core schema"):
        await verify_app_role_cannot_run_ddl(session)


@pytest.mark.asyncio
async def test_verify_app_role_fails_when_ddl_drop_succeeds() -> None:
    """If DROP TABLE unexpectedly succeeds, DDLPermissionViolationError is raised."""
    session = AsyncMock()

    mock_dml_result = MagicMock()
    mock_dml_result.scalar.return_value = 1

    permission_denied = ProgrammingError(
        statement="CREATE TABLE ...",
        params={},
        orig=Exception("permission denied for schema core"),
    )

    session.execute.side_effect = [
        mock_dml_result,  # SELECT 1
        permission_denied,  # CREATE TABLE fails
        MagicMock(),  # DROP TABLE succeeds!
    ]

    with pytest.raises(DDLPermissionViolationError, match="DROP TABLE in core schema"):
        await verify_app_role_cannot_run_ddl(session)
