"""Tests for module protocol, module registry, and template module."""

from __future__ import annotations

import compileall
import types
from pathlib import Path
from typing import Any

import pytest

from sahayak.core.module import Deps, HealthStatus, Module, ModuleRegistry, get_registry
from sahayak.modules._template.adapters.sample_repo import InMemoryPingRepository
from sahayak.modules._template.models import PingAudit, TemplateBase
from sahayak.modules._template.module import module as template_module
from sahayak.modules._template.service.sample import TemplateService
from sahayak.modules._template.tools.ping import ping_echo


def test_template_module_implements_protocol() -> None:
    """Verify that template module instance conforms to the Module protocol."""
    assert isinstance(template_module, Module)
    assert template_module.name == "_template"
    assert template_module.version == "0.1.0"
    assert template_module.migrations_path() is None

    health = template_module.health()
    assert isinstance(health, HealthStatus)
    assert health.healthy is True

    assert template_module.export_user_data("user_123") == {}
    # delete_user_data, on_event, and register_jobs should execute without exception
    template_module.delete_user_data("user_123")
    template_module.on_event({"type": "test"})
    template_module.register_jobs(None)


def test_template_directory_compiles() -> None:
    """CI check that the template module package compiles cleanly."""
    template_dir = Path("src/sahayak/modules/_template")
    assert template_dir.is_dir()
    success = compileall.compile_dir(template_dir, quiet=1, force=True)
    assert success is True


def test_module_registry_load_and_get() -> None:
    """Registry should load configured modules and provide access to them."""
    reg = ModuleRegistry()
    reg.load(("_template",))

    mod = reg.get("_template")
    assert mod is not None
    assert mod.name == "_template"
    assert "_template" in reg.modules

    health_map = reg.health_all()
    assert "_template" in health_map
    assert health_map["_template"].healthy is True

    # Events and jobs
    dispatched: list[Any] = []
    reg.dispatch_event({"event": "test"})
    reg.register_all_jobs(dispatched)

    reg.clear()
    assert len(reg.modules) == 0
    assert reg.get("_template") is None


def test_module_registry_unknown_module_fails_loudly() -> None:
    """Registry must raise RuntimeError on unknown module names."""
    reg = ModuleRegistry()
    with pytest.raises(RuntimeError, match="cannot import module 'nonexistent'"):
        reg.load(("nonexistent",))


def test_module_registry_missing_module_attribute(monkeypatch: pytest.MonkeyPatch) -> None:
    """Registry must raise RuntimeError if exported package has no 'module' attribute."""
    dummy_pkg = types.ModuleType("sahayak.modules.dummy")
    monkeypatch.setattr("importlib.import_module", lambda name: dummy_pkg)

    reg = ModuleRegistry()
    with pytest.raises(RuntimeError, match="must export a 'module' attribute"):
        reg.load(("dummy",))


def test_module_registry_invalid_protocol(monkeypatch: pytest.MonkeyPatch) -> None:
    """Registry must raise RuntimeError if exported module does not satisfy Module protocol."""
    dummy_pkg = types.ModuleType("sahayak.modules.dummy")
    dummy_pkg.module = object()  # type: ignore[attr-defined]
    monkeypatch.setattr("importlib.import_module", lambda name: dummy_pkg)

    reg = ModuleRegistry()
    with pytest.raises(RuntimeError, match="does not satisfy the Module protocol"):
        reg.load(("dummy",))


def test_module_registry_tool_registration() -> None:
    """register_all_tools should call register_tools on each loaded module."""
    reg = ModuleRegistry()
    reg.load(("_template",))

    class MockMCP:
        def __init__(self) -> None:
            self.tools: dict[str, Any] = {}

        def tool(self, name: str, description: str) -> Any:
            def decorator(fn: Any) -> Any:
                self.tools[name] = {"fn": fn, "description": description}
                return fn

            return decorator

    mock_mcp = MockMCP()
    deps = Deps()
    reg.register_all_tools(mock_mcp, deps)

    assert "ping_echo" in mock_mcp.tools
    assert "connectivity" in mock_mcp.tools["ping_echo"]["description"]


def test_template_module_add_tool_fallback() -> None:
    """register_tools should support add_tool if tool decorator is absent."""

    class MockAddToolMCP:
        def __init__(self) -> None:
            self.tools: dict[str, Any] = {}

        def add_tool(self, fn: Any, name: str, description: str) -> None:
            self.tools[name] = {"fn": fn, "description": description}

    mock_mcp = MockAddToolMCP()
    template_module.register_tools(mock_mcp, Deps())
    assert "ping_echo" in mock_mcp.tools


@pytest.mark.asyncio
async def test_ping_echo_tool() -> None:
    """Verify ping_echo tool execution and response envelope."""
    resp = await ping_echo(message="hello", request_id="req_001")
    assert resp["ok"] is True
    assert "Pong. echo: hello" in resp["spoken_summary"]
    assert resp["data"] == {"echo": "echo: hello", "received_length": 5}
    assert resp["meta"]["module"] == "_template"
    assert resp["meta"]["request_id"] == "req_001"


@pytest.mark.asyncio
async def test_template_service_and_repo() -> None:
    """Verify TemplateService with InMemoryPingRepository."""
    repo = InMemoryPingRepository()
    service = TemplateService(repo=repo)
    result = await service.process_ping("test")
    assert result == "echo: test"
    assert await repo.get_ping_count() == 1


def test_template_models() -> None:
    """Verify SQLAlchemy model definition for template schema."""
    audit = PingAudit(id="uuid-123", message="ping")
    assert audit.id == "uuid-123"
    assert audit.message == "ping"
    assert TemplateBase.metadata.schema == "_template"


def test_get_registry_singleton() -> None:
    """get_registry should return the process-wide singleton."""
    r1 = get_registry()
    r2 = get_registry()
    assert r1 is r2
