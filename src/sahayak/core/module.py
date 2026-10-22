"""Module protocol, dependency container, and discovery registry.

Every feature module implements the ``Module`` protocol and is loaded
by the ``ModuleRegistry`` from the ``ENABLED_MODULES`` configuration.
Modules receive all infrastructure through the ``Deps`` container so
they never construct databases, caches, or clients themselves.
"""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from sahayak.core.cache import Cache
    from sahayak.core.db.session import SessionFactory

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Deps:
    """Infrastructure dependencies injected into every module.

    Modules receive a ``Deps`` instance during registration and use it
    to access shared infrastructure without importing adapters directly.
    """

    session_factory: SessionFactory | Any = None
    cache: Cache | Any = None
    # Extended by later tasks: llm_client, event_bus, clock, principal_accessor


@dataclass(frozen=True)
class HealthStatus:
    """Result of a module's self-check."""

    healthy: bool
    detail: str = ""


@runtime_checkable
class Module(Protocol):
    """The contract every feature module must satisfy."""

    @property
    def name(self) -> str:
        """Unique module identifier matching the ``ENABLED_MODULES`` entry."""
        ...

    @property
    def version(self) -> str:
        """Semver of this module's tool surface."""
        ...

    def register_tools(self, mcp: Any, deps: Deps) -> None:
        """Register MCP tools provided by this module.

        Args:
            mcp: The FastMCP server instance.
            deps: Shared infrastructure dependencies.
        """
        ...

    def register_jobs(self, worker: Any) -> None:
        """Register background jobs owned by this module.

        Args:
            worker: The background worker registry.
        """
        ...

    def migrations_path(self) -> str | None:
        """Return the filesystem path to this module's Alembic migrations.

        Returns:
            An absolute path string, or ``None`` if the module has no
            migrations.
        """
        ...

    def health(self) -> HealthStatus:
        """Report whether this module's dependencies are reachable."""
        ...

    def on_event(self, event: Any) -> None:
        """Handle a dispatched domain event.

        Args:
            event: The domain event instance.
        """
        ...

    def export_user_data(self, user_id: str) -> dict[str, Any]:
        """Return all data owned by the given user for privacy export.

        Args:
            user_id: The platform user identifier.

        Returns:
            A JSON-serializable dictionary keyed by data category.
        """
        ...

    def delete_user_data(self, user_id: str) -> None:
        """Permanently erase all data owned by the given user.

        Args:
            user_id: The platform user identifier.
        """
        ...


class ModuleRegistry:
    """Discover, validate, and hold references to enabled modules.

    Raises:
        RuntimeError: If a module listed in ``ENABLED_MODULES`` cannot be
            imported or does not satisfy the ``Module`` protocol.
    """

    def __init__(self) -> None:
        self._modules: dict[str, Module] = {}

    @property
    def modules(self) -> dict[str, Module]:
        """Return the registered modules keyed by name."""
        return dict(self._modules)

    def register(self, module: Module) -> None:
        """Register a module instance directly."""
        self._modules[module.name] = module
        logger.info("registered module %s v%s", module.name, module.version)

    def load(self, enabled_names: tuple[str, ...] | list[str]) -> None:
        """Import and register the modules listed in configuration.

        Each module must be a Python package at
        ``sahayak.modules.<name>`` exporting a ``module`` attribute that
        satisfies the ``Module`` protocol.

        Args:
            enabled_names: Module names from ``ENABLED_MODULES``.

        Raises:
            RuntimeError: On import failure or protocol violation.
        """
        for name in enabled_names:
            module_path = f"sahayak.modules.{name}"
            try:
                pkg = importlib.import_module(module_path)
            except ImportError as exc:
                if not name.startswith("_"):
                    fallback_path = f"sahayak.modules._{name}"
                    try:
                        pkg = importlib.import_module(fallback_path)
                        module_path = fallback_path
                    except ImportError:
                        msg = f"cannot import module {name!r} from {module_path}: {exc}"
                        raise RuntimeError(msg) from exc
                else:
                    msg = f"cannot import module {name!r} from {module_path}: {exc}"
                    raise RuntimeError(msg) from exc

            instance = getattr(pkg, "module", None)
            if instance is None:
                msg = f"module package {module_path} must export a 'module' attribute"
                raise RuntimeError(msg)

            if not isinstance(instance, Module):
                msg = (
                    f"module {name!r} does not satisfy the Module protocol "
                    f"(got {type(instance).__name__})"
                )
                raise RuntimeError(msg)

            self._modules[name] = instance
            logger.info("registered module %s v%s", name, instance.version)

    def register_all_tools(self, mcp: Any, deps: Deps) -> None:
        """Call ``register_tools`` on every loaded module.

        Args:
            mcp: The FastMCP server instance.
            deps: Shared infrastructure dependencies.
        """
        for mod in self._modules.values():
            mod.register_tools(mcp, deps)

    def register_all_jobs(self, worker: Any) -> None:
        """Call ``register_jobs`` on every loaded module.

        Args:
            worker: The background worker registry.
        """
        for mod in self._modules.values():
            mod.register_jobs(worker)

    def dispatch_event(self, event: Any) -> None:
        """Dispatch an event to all loaded modules.

        Args:
            event: The domain event instance.
        """
        for mod in self._modules.values():
            mod.on_event(event)

    def health_all(self) -> dict[str, HealthStatus]:
        """Check health status across all registered modules."""
        return {name: mod.health() for name, mod in self._modules.items()}

    def get(self, name: str) -> Module | None:
        """Return a module by name or ``None`` if not registered."""
        return self._modules.get(name)

    def clear(self) -> None:
        """Clear all registered modules (used in tests)."""
        self._modules.clear()


_registry = ModuleRegistry()


def get_registry() -> ModuleRegistry:
    """Return the process-wide module registry singleton."""
    return _registry
