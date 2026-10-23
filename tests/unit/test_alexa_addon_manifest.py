"""Unit tests for the Alexa+ add-on manifest (T4.5)."""

from __future__ import annotations

import json
from pathlib import Path


def test_alexa_addon_manifest_structure() -> None:
    """Verify alexa/addon.json exists and adheres to Alexa+ MCP schema requirements."""
    root = Path(__file__).resolve().parents[2]
    manifest_file = root / "alexa" / "addon.json"
    assert manifest_file.exists(), "alexa/addon.json must exist"

    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))

    assert manifest["name"] == "Sahayak"
    assert "version" in manifest
    assert "locales" in manifest
    assert "en-US" in manifest["locales"]
    assert "en-IN" in manifest["locales"]

    # Verify example phrases
    en_us = manifest["locales"]["en-US"]
    assert "examplePhrases" in en_us
    phrases = en_us["examplePhrases"]
    assert len(phrases) >= 5

    # Check key PRD §19.1 phrases
    assert any("photosynthesis" in p.lower() for p in phrases)
    assert any("flashcard" in p.lower() for p in phrases)
    assert any("study plan" in p.lower() for p in phrases)
    assert any("quizzes" in p.lower() for p in phrases)
    assert any("brief" in p.lower() for p in phrases)

    # Server configuration
    assert manifest["server"]["type"] == "MCP"
    assert manifest["server"]["transport"] == "STREAMABLE_HTTP"
    assert "/mcp" in manifest["server"]["uri"]

    # Account linking configuration
    al = manifest["accountLinking"]
    assert al["type"] == "AUTH_CODE"
    assert "scopes" in al
    scopes = al["scopes"]
    assert "openid" in scopes
    assert "email" in scopes
    assert "sahayak-api/academics.read" in scopes
    assert "sahayak-api/academics.write" in scopes
