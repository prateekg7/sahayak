"""Settings module satisfying the Module protocol (T13.3)."""

from __future__ import annotations

import logging
from typing import Any

from sahayak.core.flags import UserPreferenceService, set_user_preference_service
from sahayak.core.module import Deps, HealthStatus
from sahayak.modules.settings.tools import SETTINGS_DESCRIPTION, settings

logger = logging.getLogger(__name__)


class SettingsModule:
    """Provides user preferences and module toggle capabilities."""

    def __init__(self) -> None:
        self._deps: Deps | None = None

    @property
    def name(self) -> str:
        return "settings"

    @property
    def version(self) -> str:
        return "0.1.0"

    def register_tools(self, mcp: Any, deps: Deps) -> None:
        """Register MCP tools for assistant preferences."""
        self._deps = deps
        if deps.session_factory is not None:
            pref_service = UserPreferenceService(session_factory=deps.session_factory)
            set_user_preference_service(pref_service)

        tool_decorator = getattr(mcp, "tool", None)
        if callable(tool_decorator):
            tool_decorator(name="settings", description=SETTINGS_DESCRIPTION)(settings)
        elif hasattr(mcp, "add_tool"):
            mcp.add_tool(settings, name="settings", description=SETTINGS_DESCRIPTION)

    def register_jobs(self, worker: Any) -> None:
        """Register background jobs for settings module."""
        pass

    def migrations_path(self) -> str | None:
        """Settings schema is part of core migrations."""
        return None

    def health(self) -> HealthStatus:
        """Report health status of settings module."""
        return HealthStatus(healthy=True, detail="Settings module operational")

    def on_event(self, event: Any) -> None:
        """Handle dispatched events."""
        pass

    async def export_user_data(self, user_id: str) -> dict[str, Any]:
        """Export user preferences."""
        import uuid

        from sahayak.core.flags import get_user_preference_service

        try:
            uid = uuid.UUID(user_id)
            disabled = await get_user_preference_service().get_disabled_modules(uid)
            return {"disabled_modules": sorted(list(disabled))}
        except Exception:
            return {"disabled_modules": []}

    async def delete_user_data(self, user_id: str) -> None:
        """Permanently delete user preferences."""
        import uuid

        from sqlalchemy import delete

        from sahayak.core.db.session import UnitOfWork
        from sahayak.core.flags import UserPreferenceRecord

        if self._deps is not None and self._deps.session_factory is not None:
            try:
                uid = uuid.UUID(user_id)
            except ValueError:
                return

            try:
                async with UnitOfWork(self._deps.session_factory) as uow:
                    await uow.session.execute(
                        delete(UserPreferenceRecord).where(UserPreferenceRecord.user_id == uid)
                    )
            except Exception as exc:
                logger.warning("Failed to delete user preferences for user_id=%s: %s", user_id, exc)


module = SettingsModule()
