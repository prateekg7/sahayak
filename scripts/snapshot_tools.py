"""Generate or verify the public tool schema snapshot (T0.11).

Any modification to public tool names, parameters, or descriptions requires
an explicit update to tests/snapshots/tools.json because changes require
an Alexa+ add-on redeploy (PRD §9.2).
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any

from sahayak.core.config import get_settings
from sahayak.core.mcp_server import create_mcp_server
from sahayak.core.module import ModuleRegistry

SNAPSHOT_PATH = Path("tests/snapshots/tools.json")


def generate_snapshot(modules: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
    """Generate a sorted, serializable list of tool definitions."""
    settings = get_settings()
    if modules is not None:
        enabled = modules
    elif "ENABLED_MODULES" in os.environ:
        enabled = settings.enabled_modules
    else:
        candidates = [
            "academics",
            "productivity",
            "finance",
            "health",
            "career",
            "home",
            "business",
            "language",
            "local_info",
            "civic",
        ]
        available: list[str] = []
        for name in candidates:
            try:
                importlib.import_module(f"sahayak.modules.{name}")
                available.append(name)
            except ImportError:
                pass
        enabled = tuple(available) if available else settings.enabled_modules
    registry = ModuleRegistry()
    try:
        registry.load(enabled)
    except RuntimeError:
        # Fallback to _template when feature modules are not yet built
        registry.load(("_template",))

    server = create_mcp_server(settings=settings, registry=registry)
    tools = server._tool_manager.list_tools()
    if not tools:
        registry = ModuleRegistry()
        registry.load(("_template",))
        server = create_mcp_server(settings=settings, registry=registry)
        tools = server._tool_manager.list_tools()

    snapshot_entries: list[dict[str, Any]] = []
    for tool in sorted(tools, key=lambda t: t.name):
        snapshot_entries.append(
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            }
        )
    return snapshot_entries


def write_snapshot(path: Path = SNAPSHOT_PATH) -> None:
    """Write current tool definitions to the snapshot file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tools = generate_snapshot()
    serialized = json.dumps(tools, indent=2, sort_keys=True) + "\n"
    path.write_text(serialized, encoding="utf-8")
    print(f"Wrote {len(tools)} tools to {path}")


def verify_snapshot(path: Path = SNAPSHOT_PATH) -> bool:
    """Return True if current tools match the committed snapshot exactly."""
    if not path.is_file():
        print(f"Snapshot file {path} does not exist. Run 'make snapshot'.", file=sys.stderr)
        return False

    committed_text = path.read_text(encoding="utf-8")
    current_tools = generate_snapshot()
    current_text = json.dumps(current_tools, indent=2, sort_keys=True) + "\n"

    if committed_text != current_text:
        print(
            "ERROR: MCP tool surface has changed. Run 'make snapshot' to acknowledge "
            "and update the committed snapshot (requires 'alexa-ai deploy').",
            file=sys.stderr,
        )
        return False
    return True


def main() -> None:
    """Command-line entry point for snapshot generation and verification."""
    parser = argparse.ArgumentParser(description="Tool snapshot generator and verifier.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify snapshot matches without writing.",
    )
    args = parser.parse_args()

    if args.check:
        if not verify_snapshot():
            sys.exit(1)
        print("Tool snapshot check passed.")
    else:
        write_snapshot()


if __name__ == "__main__":
    main()
