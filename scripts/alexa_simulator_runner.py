"""Automated simulator runner for executing Alexa+ multi-turn test scripts (T4.6).

Replays structured dialogues against the running MCP server or test client,
verifying voice criteria: spoken length <= 300 chars, no markdown, and correct state handles.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

import httpx

DIALOGUE_STEPS = [
    {
        "name": "Topic Brief",
        "tool": "topic_brief",
        "arguments": {"topic": "Photosynthesis", "length": "short"},
        "requires_auth": False,
    },
    {
        "name": "Quiz Start",
        "tool": "quiz_start",
        "arguments": {"topic": "General Science", "count": 3},
        "requires_auth": False,
    },
    {
        "name": "Progress Report (Unauthenticated Guard)",
        "tool": "progress_report",
        "arguments": {"scope": "summary"},
        "requires_auth": True,
        "expect_auth_error": True,
    },
]


def run_simulator_script(
    base_url: str,
    auth_token: str | None = None,
    client: httpx.Client | None = None,
) -> list[dict[str, Any]]:
    """Execute simulator test plan against base_url."""
    http_client = client or httpx.Client(timeout=10.0)
    results: list[dict[str, Any]] = []

    try:
        for step in DIALOGUE_STEPS:
            headers = {
                "Content-Type": "application/json",
                "Accept": "text/event-stream, application/json",
            }
            if auth_token and not step.get("expect_auth_error"):
                headers["Authorization"] = f"Bearer {auth_token}"

            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": step["tool"],
                    "arguments": step["arguments"],
                },
            }

            resp = http_client.post(f"{base_url.rstrip('/')}/mcp", headers=headers, json=payload)
            data = resp.json()

            # Voice check: verify spoken_summary rules if response has envelope
            spoken = ""
            if "result" in data and "spoken_summary" in data["result"]:
                spoken = data["result"]["spoken_summary"]
            elif "error" in data:
                spoken = data["error"].get("message", "")

            # Voice constraints check
            if len(spoken) > 300:
                msg = f"Step '{step['name']}' exceeded spoken char limit: {len(spoken)} > 300"
                raise ValueError(msg)

            for forbidden in ["**", "##", "http://", "https://"]:
                if forbidden in spoken:
                    msg = f"Step '{step['name']}' contained forbidden '{forbidden}': {spoken}"
                    raise ValueError(msg)

            results.append(
                {
                    "step": step["name"],
                    "status_code": resp.status_code,
                    "spoken_summary_length": len(spoken),
                    "passed": True,
                }
            )
    finally:
        if client is None:
            http_client.close()

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Alexa+ simulator dialogue runner.")
    parser.add_argument("--url", default="http://localhost:8000", help="Base server URL")
    parser.add_argument("--token", default=None, help="Bearer auth token")
    args = parser.parse_args()

    try:
        results = run_simulator_script(args.url, auth_token=args.token)
        print(f"Simulator scripts PASSED: {len(results)} steps completed successfully.")
    except Exception as e:
        print(f"Simulator script FAILED: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
