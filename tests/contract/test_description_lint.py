"""Contract tests linting tool descriptions for voice discovery rules (T0.11).

PRD §9.2 and AGENTS.md §7.4 require:
1. One sentence of what the tool does.
2. "Use when …" with an example utterance (drives Alexa+'s selection).
3. "Do not use for …" pointing to sibling tools.
"""

from __future__ import annotations

import re

from sahayak.core.config import get_settings
from sahayak.core.mcp_server import create_mcp_server
from sahayak.core.module import ModuleRegistry


def test_tool_descriptions_conform_to_voice_lint_rules() -> None:
    """All registered tool descriptions must satisfy the required voice format."""
    settings = get_settings()
    registry = ModuleRegistry()
    registry.load(("_template",))
    server = create_mcp_server(settings=settings, registry=registry)

    tools = server._tool_manager.list_tools()
    assert len(tools) > 0, "No tools registered to test"

    for tool in tools:
        desc = tool.description or ""
        assert desc, f"Tool {tool.name!r} has an empty description"

        # Rule 2: "Use when ..."
        assert "use when" in desc.lower(), (
            f"Tool {tool.name!r} description must contain 'Use when ...'. Got: {desc!r}"
        )

        # Rule 2: example utterance (single or double quotes or e.g.)
        has_quote = bool(re.search(r"['\"].*?['\"]", desc))
        assert has_quote, (
            f"Tool {tool.name!r} description must contain an example utterance in quotes. "
            f"Got: {desc!r}"
        )

        # Rule 3: "Do not use for ..."
        assert "do not use for" in desc.lower(), (
            f"Tool {tool.name!r} description must contain 'Do not use for ...'. Got: {desc!r}"
        )
