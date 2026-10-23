"""Unit tests for threat model, operational runbooks, and restore drill (T4.8)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from scripts.db_restore_drill import execute_restore_drill


def test_stride_threat_model_coverage() -> None:
    """Verify threat model covers all STRIDE categories and key mitigations."""
    root = Path(__file__).resolve().parents[2]
    tm_file = root / "docs" / "security" / "threat-model.md"
    assert tm_file.exists(), "docs/security/threat-model.md must exist"

    content = tm_file.read_text(encoding="utf-8")
    for category in [
        "Spoofing",
        "Tampering",
        "Repudiation",
        "Information Disclosure",
        "Denial of Service",
        "Elevation of Privilege",
    ]:
        assert category in content, f"STRIDE category '{category}' must be documented"

    assert "JWKS" in content
    assert "Pydantic" in content
    assert "audit_log" in content
    assert "redact" in content
    assert "rate limiter" in content or "rate-limit" in content


def test_all_operational_runbooks_exist() -> None:
    """Verify all 7 required operational runbooks exist and contain actionable procedures."""
    root = Path(__file__).resolve().parents[2]
    runbooks_dir = root / "docs" / "runbooks"
    required = [
        "deploy.md",
        "rollback.md",
        "provider-outage.md",
        "key-rotation.md",
        "backup-restore.md",
        "add-on-redeploy.md",
        "user-data-request.md",
    ]
    for rb in required:
        file_path = runbooks_dir / rb
        assert file_path.exists(), f"Runbook {rb} must exist"
        assert len(file_path.read_text(encoding="utf-8")) > 100


@pytest.mark.asyncio
async def test_db_restore_drill_execution() -> None:
    """Verify restore drill queries information schema and calculates timings."""
    mock_session = AsyncMock()

    mock_schemas_res = MagicMock()
    mock_schemas_res.fetchall.return_value = [("core",), ("academics",)]

    mock_tables_res = MagicMock()
    mock_tables_res.fetchall.return_value = [("quizzes",), ("cards",), ("users",)]

    mock_session.execute.side_effect = [mock_schemas_res, mock_tables_res]

    results = await execute_restore_drill(mock_session)
    assert results["status"] == "success"
    assert results["found_schemas"] == ["academics", "core"]
    assert results["table_count"] == 3
    assert results["rto_target_met"] is True
    assert results["duration_seconds"] >= 0
