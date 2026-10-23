"""Career module definition satisfying the Module protocol (T8.1, T8.2)."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select

from sahayak.core.db.session import UnitOfWork
from sahayak.core.module import Deps, HealthStatus
from sahayak.modules.career.models import (
    Application,
    DailyPractice,
    InterviewSession,
    InterviewTurn,
)


class CareerModule:
    """Career module providing mock interview practice, applications tracking, and coaching."""

    def __init__(self) -> None:
        self._deps: Deps | None = None
        self._api: Any = None

    @property
    def name(self) -> str:
        return "career"

    @property
    def version(self) -> str:
        return "0.1.0"

    @property
    def api(self) -> Any:
        if self._api is None:
            if self._deps is None or self._deps.session_factory is None:
                return None
            from sahayak.modules.career.api import CareerAPI

            self._api = CareerAPI(session_factory=self._deps.session_factory)
        return self._api

    def register_tools(self, mcp: Any, deps: Deps) -> None:
        """Register MCP tools provided by the career module."""
        self._deps = deps
        if deps.session_factory is not None:
            from sahayak.modules.career.service.applications import ApplicationService
            from sahayak.modules.career.service.interview import InterviewService
            from sahayak.modules.career.service.practice import CareerPracticeService
            from sahayak.modules.career.tools.application_tracker import (
                set_application_service,
            )
            from sahayak.modules.career.tools.career_practice import (
                set_practice_service,
            )
            from sahayak.modules.career.tools.interview_practice import (
                set_interview_service,
            )

            llm_client = getattr(deps, "llm", None)
            clock_fn = getattr(deps, "clock", None)

            interview_service = InterviewService(
                session_factory=deps.session_factory,
                llm_client=llm_client,
            )
            set_interview_service(interview_service)

            app_service = ApplicationService(
                session_factory=deps.session_factory,
                clock=clock_fn,
            )
            set_application_service(app_service)

            practice_service = CareerPracticeService(
                session_factory=deps.session_factory,
                llm_client=llm_client,
            )
            set_practice_service(practice_service)

        from sahayak.modules.career.tools.application_tracker import (
            APPLICATION_TRACKER_DESCRIPTION,
            application_tracker,
        )
        from sahayak.modules.career.tools.career_practice import (
            CAREER_PRACTICE_DESCRIPTION,
            career_practice,
        )
        from sahayak.modules.career.tools.interview_practice import (
            INTERVIEW_PRACTICE_DESCRIPTION,
            interview_practice,
        )

        tool_decorator = getattr(mcp, "tool", None)
        if callable(tool_decorator):
            tool_decorator(name="interview_practice", description=INTERVIEW_PRACTICE_DESCRIPTION)(
                interview_practice
            )
            tool_decorator(name="application_tracker", description=APPLICATION_TRACKER_DESCRIPTION)(
                application_tracker
            )
            tool_decorator(name="career_practice", description=CAREER_PRACTICE_DESCRIPTION)(
                career_practice
            )
        elif hasattr(mcp, "add_tool"):
            mcp.add_tool(
                interview_practice,
                name="interview_practice",
                description=INTERVIEW_PRACTICE_DESCRIPTION,
            )
            mcp.add_tool(
                application_tracker,
                name="application_tracker",
                description=APPLICATION_TRACKER_DESCRIPTION,
            )
            mcp.add_tool(
                career_practice,
                name="career_practice",
                description=CAREER_PRACTICE_DESCRIPTION,
            )

    def register_jobs(self, worker: Any) -> None:
        """Register background jobs for career module."""
        pass

    def migrations_path(self) -> str | None:
        return str(Path(__file__).parent / "migrations")

    def health(self) -> HealthStatus:
        if self._deps is not None and self._deps.session_factory is None:
            return HealthStatus(healthy=False, detail="PostgreSQL session factory missing")
        return HealthStatus(healthy=True, detail="Career module is operational")

    def on_event(self, event: Any) -> None:
        """Dispatched domain events hook."""
        pass

    async def export_user_data(self, user_id: str) -> dict[str, Any]:
        """GDPR Right to Access: export user interview, application, and practice records."""
        if self._deps is None or self._deps.session_factory is None:
            return {}

        uid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
        async with UnitOfWork(self._deps.session_factory) as uow:
            res_sessions = await uow.session.execute(
                select(InterviewSession).where(InterviewSession.user_id == uid)
            )
            sessions = res_sessions.scalars().all()
            session_ids = [s.id for s in sessions]

            turns_by_session: dict[uuid.UUID, list[InterviewTurn]] = {
                sid: [] for sid in session_ids
            }
            if session_ids:
                res_turns = await uow.session.execute(
                    select(InterviewTurn).where(InterviewTurn.session_id.in_(session_ids))
                )
                for t in res_turns.scalars().all():
                    turns_by_session.setdefault(t.session_id, []).append(t)

            exported_sessions = []
            for s in sessions:
                s_dict = s.to_dict()
                s_dict["turns"] = [t.to_dict() for t in turns_by_session.get(s.id, [])]
                exported_sessions.append(s_dict)

            res_apps = await uow.session.execute(
                select(Application).where(Application.user_id == uid)
            )
            apps = res_apps.scalars().all()

            res_practice = await uow.session.execute(
                select(DailyPractice).where(DailyPractice.user_id == uid)
            )
            practices = res_practice.scalars().all()

            return {
                "interview_sessions": exported_sessions,
                "applications": [a.to_dict() for a in apps],
                "daily_practice": [p.to_dict() for p in practices],
            }

    async def delete_user_data(self, user_id: str) -> None:
        """GDPR Right to Erasure: permanently delete user career records."""
        if self._deps is None or self._deps.session_factory is None:
            return

        uid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
        async with UnitOfWork(self._deps.session_factory) as uow:
            # Delete applications
            await uow.session.execute(delete(Application).where(Application.user_id == uid))

            # Delete daily practice
            await uow.session.execute(delete(DailyPractice).where(DailyPractice.user_id == uid))

            # Delete sessions & turns
            res = await uow.session.execute(
                select(InterviewSession.id).where(InterviewSession.user_id == uid)
            )
            session_ids = list(res.scalars().all())
            if session_ids:
                await uow.session.execute(
                    delete(InterviewTurn).where(InterviewTurn.session_id.in_(session_ids))
                )
            await uow.session.execute(
                delete(InterviewSession).where(InterviewSession.user_id == uid)
            )


module = CareerModule()
