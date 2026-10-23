"""Productivity module definition satisfying the Module protocol (T5.1)."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select

from sahayak.core.db.session import UnitOfWork
from sahayak.core.module import Deps, HealthStatus
from sahayak.modules.productivity.models import FocusSession, Habit, HabitLog, Note, Task


class ProductivityModule:
    """Productivity module providing personal tasks, habits, notes, and timers."""

    def __init__(self) -> None:
        self._deps: Deps | None = None
        self._api: Any = None

    @property
    def name(self) -> str:
        return "productivity"

    @property
    def version(self) -> str:
        return "0.1.0"

    @property
    def api(self) -> Any:
        """Cross-module API instance for querying pending tasks."""
        if self._api is None:
            if self._deps is None or self._deps.session_factory is None:
                raise RuntimeError("ProductivityModule has not been initialized with dependencies")
            from sahayak.modules.productivity.api import ProductivityAPI

            clock_fn = getattr(self._deps, "clock", None)
            self._api = ProductivityAPI(
                session_factory=self._deps.session_factory,
                clock=clock_fn,
            )
        return self._api

    def register_tools(self, mcp: Any, deps: Deps) -> None:
        """Register MCP tools provided by the productivity module."""
        self._deps = deps
        if deps.session_factory is not None:
            from sahayak.modules.productivity.service.focus import FocusService
            from sahayak.modules.productivity.service.habits import HabitService
            from sahayak.modules.productivity.service.notes import NoteService
            from sahayak.modules.productivity.service.tasks import TaskService
            from sahayak.modules.productivity.tools.focus import set_focus_service
            from sahayak.modules.productivity.tools.habits import set_habit_service
            from sahayak.modules.productivity.tools.notes import set_note_service
            from sahayak.modules.productivity.tools.tasks import set_task_service

            clock_fn = getattr(deps, "clock", None)
            task_service = TaskService(session_factory=deps.session_factory, clock=clock_fn)
            set_task_service(task_service)

            habit_service = HabitService(session_factory=deps.session_factory, clock=clock_fn)
            set_habit_service(habit_service)

            note_service = NoteService(session_factory=deps.session_factory)
            set_note_service(note_service)

            focus_service = FocusService(session_factory=deps.session_factory, clock=clock_fn)
            set_focus_service(focus_service)

        from sahayak.modules.productivity.tools.focus import FOCUS_TIMER_DESCRIPTION, focus_timer
        from sahayak.modules.productivity.tools.habits import HABITS_DESCRIPTION, habits
        from sahayak.modules.productivity.tools.notes import NOTES_DESCRIPTION, notes
        from sahayak.modules.productivity.tools.tasks import TASKS_DESCRIPTION, tasks

        tool_decorator = getattr(mcp, "tool", None)
        if callable(tool_decorator):
            tool_decorator(name="tasks", description=TASKS_DESCRIPTION)(tasks)
            tool_decorator(name="habits", description=HABITS_DESCRIPTION)(habits)
            tool_decorator(name="notes", description=NOTES_DESCRIPTION)(notes)
            tool_decorator(name="focus_timer", description=FOCUS_TIMER_DESCRIPTION)(focus_timer)
        elif hasattr(mcp, "add_tool"):
            mcp.add_tool(tasks, name="tasks", description=TASKS_DESCRIPTION)
            mcp.add_tool(habits, name="habits", description=HABITS_DESCRIPTION)
            mcp.add_tool(notes, name="notes", description=NOTES_DESCRIPTION)
            mcp.add_tool(focus_timer, name="focus_timer", description=FOCUS_TIMER_DESCRIPTION)

    def register_jobs(self, worker: Any) -> None:
        """Register background jobs for productivity module."""
        pass

    def migrations_path(self) -> str | None:
        return str(Path(__file__).parent / "migrations")

    def health(self) -> HealthStatus:
        if self._deps is not None and self._deps.session_factory is None:
            return HealthStatus(healthy=False, detail="PostgreSQL session factory missing")
        return HealthStatus(healthy=True, detail="Productivity module is operational")

    def on_event(self, event: Any) -> None:
        """Dispatched domain events hook."""
        pass

    async def export_user_data(self, user_id: str) -> dict[str, Any]:
        """GDPR Right to Access: export all tasks, habits, notes, and focus sessions."""
        if self._deps is None or self._deps.session_factory is None:
            return {}

        uid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
        async with UnitOfWork(self._deps.session_factory) as uow:
            tasks_res = await uow.session.execute(select(Task).where(Task.user_id == uid))
            tasks_list = tasks_res.scalars().all()

            habits_res = await uow.session.execute(select(Habit).where(Habit.user_id == uid))
            habits_list = habits_res.scalars().all()

            logs_res = await uow.session.execute(select(HabitLog).where(HabitLog.user_id == uid))
            logs_list = logs_res.scalars().all()

            notes_res = await uow.session.execute(select(Note).where(Note.user_id == uid))
            notes_list = notes_res.scalars().all()

            sessions_res = await uow.session.execute(
                select(FocusSession).where(FocusSession.user_id == uid)
            )
            sessions_list = sessions_res.scalars().all()

            return {
                "tasks": [t.to_dict() for t in tasks_list],
                "habits": [h.to_dict() for h in habits_list],
                "habit_logs": [log.to_dict() for log in logs_list],
                "notes": [n.to_dict() for n in notes_list],
                "focus_sessions": [s.to_dict() for s in sessions_list],
            }

    async def delete_user_data(self, user_id: str) -> None:
        """GDPR Right to Erasure: permanently delete all data owned by user_id."""
        if self._deps is None or self._deps.session_factory is None:
            return

        uid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
        async with UnitOfWork(self._deps.session_factory) as uow:
            await uow.session.execute(delete(FocusSession).where(FocusSession.user_id == uid))
            await uow.session.execute(delete(Note).where(Note.user_id == uid))
            await uow.session.execute(delete(HabitLog).where(HabitLog.user_id == uid))
            await uow.session.execute(delete(Habit).where(Habit.user_id == uid))
            await uow.session.execute(delete(Task).where(Task.user_id == uid))


module = ProductivityModule()
