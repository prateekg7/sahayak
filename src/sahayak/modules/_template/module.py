"""Template module implementation — copy and adapt for real modules.

This skeleton satisfies the ``Module`` protocol and registers a sample
``ping_echo`` tool that proves the MCP wiring works end to end.
"""

from __future__ import annotations

from typing import Any

from sahayak.core.module import Deps, HealthStatus
from sahayak.modules._template.tools.ping import PING_ECHO_DESCRIPTION, ping_echo


class TemplateModule:
    """Complete example satisfying the Module protocol."""

    @property
    def name(self) -> str:
        return "_template"

    @property
    def version(self) -> str:
        return "0.1.0"

    def register_tools(self, mcp: Any, deps: Deps) -> None:
        """Register the sample ``ping_echo`` tool.

        Args:
            mcp: The FastMCP server instance or mock.
            deps: Shared infrastructure dependencies.
        """
        # Supports FastMCP decorator or direct function registration
        tool_decorator = getattr(mcp, "tool", None)
        if callable(tool_decorator):
            tool_decorator(name="ping_echo", description=PING_ECHO_DESCRIPTION)(ping_echo)
        elif hasattr(mcp, "add_tool"):
            mcp.add_tool(ping_echo, name="ping_echo", description=PING_ECHO_DESCRIPTION)

    def register_jobs(self, worker: Any) -> None:
        """Register background jobs for template module."""
        pass

    def migrations_path(self) -> str | None:
        return None

    def health(self) -> HealthStatus:
        return HealthStatus(healthy=True, detail="template module has no external dependencies")

    def on_event(self, event: Any) -> None:
        pass

    def export_user_data(self, user_id: str) -> dict[str, Any]:
        return {}

    def delete_user_data(self, user_id: str) -> None:
        pass


module = TemplateModule()
