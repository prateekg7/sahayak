"""Generate or verify public tool schema snapshots for deployment profiles (T0.11, T13.1).

Any modification to public tool names, parameters, or descriptions requires
an explicit update to tests/snapshots/tools.json and per-profile snapshots because
changes require an Alexa+ add-on redeploy (PRD §9.2, ADR 0016).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from sahayak.core.config import get_settings
from sahayak.core.mcp_server import create_mcp_server
from sahayak.core.module import ModuleRegistry
from sahayak.core.profiles import BUNDLE_PROFILES, get_profile_modules

SNAPSHOT_DIR = Path("tests/snapshots")
SNAPSHOT_PATH = SNAPSHOT_DIR / "tools.json"


def get_profile_snapshot_path(profile: str) -> Path:
    """Return file path for a profile's tool snapshot."""
    if profile.lower() == "full":
        return SNAPSHOT_PATH
    return SNAPSHOT_DIR / f"{profile.lower()}_tools.json"


def generate_snapshot(modules: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
    """Generate a sorted, serializable list of tool definitions for given modules."""
    settings = get_settings()
    if modules is not None:
        enabled = modules
    elif "DEPLOYMENT_PROFILE" in os.environ:
        enabled = get_profile_modules(os.environ["DEPLOYMENT_PROFILE"])
    elif "ENABLED_MODULES" in os.environ:
        enabled = settings.enabled_modules
    else:
        enabled = BUNDLE_PROFILES["full"]

    registry = ModuleRegistry()
    try:
        registry.load(enabled)
    except RuntimeError:
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


def write_snapshot(path: Path = SNAPSHOT_PATH, modules: tuple[str, ...] | None = None) -> None:
    """Write tool definitions to the target snapshot file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tools = generate_snapshot(modules=modules)
    serialized = json.dumps(tools, indent=2, sort_keys=True) + "\n"
    path.write_text(serialized, encoding="utf-8")
    print(f"Wrote {len(tools)} tools to {path}")


def verify_snapshot(path: Path = SNAPSHOT_PATH, modules: tuple[str, ...] | None = None) -> bool:
    """Return True if tools match the committed snapshot exactly."""
    if not path.is_file():
        print(f"Snapshot file {path} does not exist. Run 'make snapshot'.", file=sys.stderr)
        return False

    committed_text = path.read_text(encoding="utf-8")
    current_tools = generate_snapshot(modules=modules)
    current_text = json.dumps(current_tools, indent=2, sort_keys=True) + "\n"

    if committed_text != current_text:
        print(
            f"ERROR: MCP tool surface has changed for {path.name}. "
            "Run 'make snapshot' to acknowledge and update the committed snapshot "
            "(requires 'alexa-ai deploy').",
            file=sys.stderr,
        )
        return False
    return True


def write_all_profiles() -> None:
    """Write snapshots for all bundles and the full monolith."""
    for profile, modules in BUNDLE_PROFILES.items():
        path = get_profile_snapshot_path(profile)
        write_snapshot(path=path, modules=modules)


def verify_all_profiles() -> bool:
    """Verify snapshots for all bundles and the full monolith."""
    all_ok = True
    for profile, modules in BUNDLE_PROFILES.items():
        path = get_profile_snapshot_path(profile)
        if not verify_snapshot(path=path, modules=modules):
            all_ok = False
    return all_ok


def main() -> None:
    """Command-line entry point for snapshot generation and verification."""
    parser = argparse.ArgumentParser(description="Tool snapshot generator and verifier.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify snapshot matches without writing.",
    )
    parser.add_argument(
        "--profile",
        type=str,
        default=None,
        help="Target profile name (study, life, work, home, full).",
    )
    parser.add_argument(
        "--all-profiles",
        action="store_true",
        help="Generate or verify snapshots for all profiles.",
    )
    args = parser.parse_args()

    if args.all_profiles:
        if args.check:
            if not verify_all_profiles():
                sys.exit(1)
            print("All profile tool snapshot checks passed.")
        else:
            write_all_profiles()
    elif args.profile:
        modules = get_profile_modules(args.profile)
        path = get_profile_snapshot_path(args.profile)
        if args.check:
            if not verify_snapshot(path=path, modules=modules):
                sys.exit(1)
            print(f"Profile '{args.profile}' snapshot check passed.")
        else:
            write_snapshot(path=path, modules=modules)
    else:
        if args.check:
            if not verify_snapshot():
                sys.exit(1)
            print("Tool snapshot check passed.")
        else:
            write_all_profiles()


if __name__ == "__main__":
    main()
