"""Health module definition satisfying the Module protocol (T7.1, T7.2)."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select

from sahayak.core.db.session import UnitOfWork
from sahayak.core.module import Deps, HealthStatus
from sahayak.modules.health.models import HealthEntry, Medicine, MedicineDose


class HealthModule:
    """Health module providing personal health metric logging and medicine tracking.

    Covers water, meals, sleep, workouts, weight, and medicine adherence.
    """

    def __init__(self) -> None:
        self._deps: Deps | None = None
        self._api: Any = None

    @property
    def name(self) -> str:
        return "health"

    @property
    def version(self) -> str:
        return "0.1.0"

    @property
    def api(self) -> Any:
        """Cross-module API instance for querying health metrics."""
        if self._api is None:
            if self._deps is None or self._deps.session_factory is None:
                raise RuntimeError("HealthModule has not been initialized with dependencies")
            from sahayak.modules.health.api import HealthAPI

            clock_fn = getattr(self._deps, "clock", None)
            self._api = HealthAPI(
                session_factory=self._deps.session_factory,
                clock=clock_fn,
            )
        return self._api

    def register_tools(self, mcp: Any, deps: Deps) -> None:
        """Register MCP tools provided by the health module."""
        self._deps = deps
        if deps.session_factory is not None:
            from sahayak.modules.health.service.health_log import HealthLogService
            from sahayak.modules.health.service.health_summary import HealthSummaryService
            from sahayak.modules.health.tools.health_log import set_health_log_service
            from sahayak.modules.health.tools.health_summary import set_health_summary_service

            clock_fn = getattr(deps, "clock", None)
            log_service = HealthLogService(
                session_factory=deps.session_factory,
                clock=clock_fn,
            )
            set_health_log_service(log_service)

            summary_service = HealthSummaryService(
                session_factory=deps.session_factory,
                clock=clock_fn,
            )
            set_health_summary_service(summary_service)

        from sahayak.modules.health.tools.health_log import (
            HEALTH_LOG_DESCRIPTION,
            health_log,
        )
        from sahayak.modules.health.tools.health_summary import (
            HEALTH_SUMMARY_DESCRIPTION,
            health_summary,
        )

        tool_decorator = getattr(mcp, "tool", None)
        if callable(tool_decorator):
            tool_decorator(name="health_log", description=HEALTH_LOG_DESCRIPTION)(health_log)
            tool_decorator(name="health_summary", description=HEALTH_SUMMARY_DESCRIPTION)(
                health_summary
            )
        elif hasattr(mcp, "add_tool"):
            mcp.add_tool(health_log, name="health_log", description=HEALTH_LOG_DESCRIPTION)
            mcp.add_tool(
                health_summary,
                name="health_summary",
                description=HEALTH_SUMMARY_DESCRIPTION,
            )

    def register_jobs(self, worker: Any) -> None:
        """Register background jobs for health module."""
        pass

    def migrations_path(self) -> str | None:
        return str(Path(__file__).parent / "migrations")

    def health(self) -> HealthStatus:
        if self._deps is not None and self._deps.session_factory is None:
            return HealthStatus(healthy=False, detail="PostgreSQL session factory missing")
        return HealthStatus(healthy=True, detail="Health module is operational")

    def on_event(self, event: Any) -> None:
        """Dispatched domain events hook."""
        pass

    async def export_user_data(self, user_id: str) -> dict[str, Any]:
        """GDPR Right to Access: export user health entries, medicines, and doses."""
        if self._deps is None or self._deps.session_factory is None:
            return {}

        uid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
        async with UnitOfWork(self._deps.session_factory) as uow:
            res_entries = await uow.session.execute(
                select(HealthEntry).where(HealthEntry.user_id == uid)
            )
            entries = res_entries.scalars().all()

            res_meds = await uow.session.execute(select(Medicine).where(Medicine.user_id == uid))
            meds = res_meds.scalars().all()

            res_doses = await uow.session.execute(
                select(MedicineDose).where(MedicineDose.user_id == uid)
            )
            doses = res_doses.scalars().all()

            return {
                "health_entries": [e.to_dict() for e in entries],
                "health_medicines": [m.to_dict() for m in meds],
                "health_medicine_doses": [d.to_dict() for d in doses],
            }

    async def delete_user_data(self, user_id: str) -> None:
        """GDPR Right to Erasure: permanently delete user health records."""
        if self._deps is None or self._deps.session_factory is None:
            return

        uid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
        async with UnitOfWork(self._deps.session_factory) as uow:
            await uow.session.execute(delete(MedicineDose).where(MedicineDose.user_id == uid))
            await uow.session.execute(delete(Medicine).where(Medicine.user_id == uid))
            await uow.session.execute(delete(HealthEntry).where(HealthEntry.user_id == uid))


module = HealthModule()
