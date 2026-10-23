"""Unit tests for the Alexa+ test plans and simulator runner (T4.6)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest
from scripts.alexa_simulator_runner import run_simulator_script


def test_test_plans_document_exists() -> None:
    """Verify test-plans.md exists and covers all required PRD §2.1 voice dialogs."""
    root = Path(__file__).resolve().parents[2]
    doc = root / "docs" / "alexa" / "test-plans.md"
    assert doc.exists()

    content = doc.read_text(encoding="utf-8")
    assert "Quiz Happy Path" in content
    assert "Ambiguous Answers" in content
    assert "Expired Quiz" in content
    assert "Authorization Matrix" in content
    assert "Flashcards" in content
    assert "Planner" in content
    assert "Progress Report" in content
    assert "Topic Brief" in content
    assert "Local Inspector" in content
    assert "Physical Echo Device" in content


def test_simulator_runner_success() -> None:
    """Verify simulator runner parses mock voice responses and validates constraints."""
    mock_client = MagicMock(spec=httpx.Client)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "result": {
            "ok": True,
            "spoken_summary": "Here is a brief overview of photosynthesis in plants.",
            "data": {},
        }
    }
    mock_client.post.return_value = mock_resp

    results = run_simulator_script("http://testserver", client=mock_client)
    assert len(results) == 3
    assert all(r["passed"] for r in results)


def test_simulator_runner_rejects_markdown_in_speech() -> None:
    """Verify simulator runner detects and fails if speech contains markdown formatting."""
    mock_client = MagicMock(spec=httpx.Client)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "result": {
            "ok": True,
            "spoken_summary": "Here is **photosynthesis** overview.",  # Forbidden markdown
        }
    }
    mock_client.post.return_value = mock_resp

    with pytest.raises(ValueError, match="contained forbidden"):
        run_simulator_script("http://testserver", client=mock_client)


def test_simulator_runner_rejects_overlong_speech() -> None:
    """Verify simulator runner fails if spoken summary exceeds 300 characters."""
    mock_client = MagicMock(spec=httpx.Client)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "result": {
            "ok": True,
            "spoken_summary": "A" * 305,  # Exceeds 300
        }
    }
    mock_client.post.return_value = mock_resp

    with pytest.raises(ValueError, match="exceeded spoken char limit"):
        run_simulator_script("http://testserver", client=mock_client)
