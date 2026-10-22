"""Contract tests verifying tool schema snapshots (T0.11)."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.snapshot_tools import SNAPSHOT_PATH, generate_snapshot, verify_snapshot


def test_committed_tool_snapshot_matches_current_definitions() -> None:
    """The committed tools.json snapshot must match the active server tools."""
    assert SNAPSHOT_PATH.is_file(), f"Missing snapshot file at {SNAPSHOT_PATH}"
    assert verify_snapshot() is True, "Tool surface has changed. Run 'make snapshot'."


def test_snapshot_fails_when_tool_surface_mutates(tmp_path: Path) -> None:
    """Modifying a tool parameter or description without updating snapshot must fail."""
    test_file = tmp_path / "tools.json"
    current_tools = generate_snapshot()
    assert len(current_tools) > 0

    # Write modified snapshot
    mutated = json.loads(json.dumps(current_tools))
    mutated[0]["description"] = "Changed description"
    test_file.write_text(json.dumps(mutated, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    assert verify_snapshot(test_file) is False
