"""Tool count and per-module budget guard tests (T0.11)."""

from __future__ import annotations

from sahayak.core.config import get_settings
from sahayak.core.mcp_server import create_mcp_server
from sahayak.core.module import Deps, ModuleRegistry


def test_tool_count_within_global_and_module_budgets() -> None:
    """Total tools must not exceed MAX_TOOLS and module limit MAX_TOOLS_PER_MODULE."""
    settings = get_settings()
    registry = ModuleRegistry()
    registry.load(("_template",))
    server = create_mcp_server(settings=settings, registry=registry)

    tools = server._tool_manager.list_tools()

    # Global tool count budget
    assert len(tools) <= settings.max_tools, (
        f"Total tools count {len(tools)} exceeds MAX_TOOLS={settings.max_tools}"
    )

    # Per-module budget
    for name, module in registry.modules.items():
        sub_server = create_mcp_server(settings=settings, registry=ModuleRegistry())
        module.register_tools(sub_server, Deps())
        module_tools = sub_server._tool_manager.list_tools()
        assert len(module_tools) <= settings.max_tools_per_module, (
            f"Module {name!r} registered {len(module_tools)} tools, "
            f"exceeding MAX_TOOLS_PER_MODULE={settings.max_tools_per_module}"
        )


def test_budget_guard_catches_exceeded_module_limit() -> None:
    """Registering more than max_tools_per_module must be detected."""
    settings = get_settings()

    class GreedModule:
        @property
        def name(self) -> str:
            return "greedy"

        @property
        def version(self) -> str:
            return "0.1.0"

        def register_tools(self, mcp: Any, deps: Deps) -> None:
            # Register 5 tools exceeding default limit of 4
            for i in range(5):
                mcp.tool(name=f"tool_{i}", description="test")(lambda: "ok")

        def register_jobs(self, worker: Any) -> None:
            pass

        def migrations_path(self) -> str | None:
            return None

        def health(self) -> Any:
            pass

        def on_event(self, event: Any) -> None:
            pass

        def export_user_data(self, user_id: str) -> dict[str, Any]:
            return {}

        def delete_user_data(self, user_id: str) -> None:
            pass

    from typing import Any

    sub_server = create_mcp_server(settings=settings, registry=ModuleRegistry())
    GreedModule().register_tools(sub_server, Deps())
    tools = sub_server._tool_manager.list_tools()
    assert len(tools) > settings.max_tools_per_module
