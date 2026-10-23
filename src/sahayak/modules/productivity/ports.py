"""Port interfaces for the productivity module (T5.1)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Protocol

from sahayak.modules.productivity.models import FocusSession, Habit, HabitLog, Note, Task


class TaskRepositoryPort(Protocol):
    """Repository port interface for task persistence."""

    async def create_task(
        self,
        user_id: uuid.UUID,
        title: str,
        list_name: str = "inbox",
        priority: str = "medium",
        status: str = "pending",
        due_at: datetime | None = None,
        tags: list[str] | None = None,
    ) -> Task:
        """Create and persist a new task."""
        ...

    async def get_task(self, user_id: uuid.UUID, task_id: uuid.UUID) -> Task | None:
        """Retrieve task by ID, scoped by user_id."""
        ...

    async def list_tasks(
        self,
        user_id: uuid.UUID,
        status: str | None = None,
        list_name: str | None = None,
        limit: int = 5,
    ) -> list[Task]:
        """List tasks scoped by user_id with optional status and list filters."""
        ...

    async def update_task_status(
        self,
        user_id: uuid.UUID,
        task_id: uuid.UUID,
        status: str,
    ) -> Task | None:
        """Update task status (e.g. pending -> completed), setting completed_at if completed."""
        ...

    async def reschedule_task(
        self,
        user_id: uuid.UUID,
        task_id: uuid.UUID,
        due_at: datetime,
    ) -> Task | None:
        """Update task due date, scoped by user_id."""
        ...

    async def delete_task(self, user_id: uuid.UUID, task_id: uuid.UUID) -> bool:
        """Delete task by ID, scoped by user_id."""
        ...

    async def count_pending_tasks(
        self,
        user_id: uuid.UUID,
        list_name: str | None = None,
    ) -> int:
        """Count pending tasks for a user."""
        ...

    async def get_due_today_tasks(
        self,
        user_id: uuid.UUID,
        start_of_day: datetime,
        end_of_day: datetime,
    ) -> list[Task]:
        """Get tasks due on a specific local calendar day."""
        ...


class HabitRepositoryPort(Protocol):
    """Repository port interface for habit tracking and completion logging."""

    async def create_habit(
        self,
        user_id: uuid.UUID,
        name: str,
        target_frequency: str = "daily",
    ) -> Habit:
        """Create and persist a new habit."""
        ...

    async def get_habit(self, user_id: uuid.UUID, habit_id: uuid.UUID) -> Habit | None:
        """Retrieve habit by ID, scoped by user_id."""
        ...

    async def get_habit_by_name(self, user_id: uuid.UUID, name: str) -> Habit | None:
        """Retrieve habit by case-insensitive name, scoped by user_id."""
        ...

    async def list_habits(
        self,
        user_id: uuid.UUID,
        include_archived: bool = False,
    ) -> list[Habit]:
        """List all habits owned by a user."""
        ...

    async def log_habit(
        self,
        user_id: uuid.UUID,
        habit_id: uuid.UUID,
        logged_date: date,
        notes: str | None = None,
    ) -> tuple[HabitLog, bool]:
        """Log a habit completion on a specific calendar date (idempotent on habit_id + date)."""
        ...

    async def get_habit_logs(
        self,
        habit_id: uuid.UUID,
        limit: int = 365,
    ) -> list[HabitLog]:
        """Get recent logs for a habit ordered by date descending."""
        ...

    async def update_habit_streak(
        self,
        habit_id: uuid.UUID,
        streak_current: int,
        streak_longest: int,
        last_logged_date: date,
    ) -> Habit | None:
        """Update habit's streak metrics and last completion date."""
        ...

    async def archive_habit(
        self,
        user_id: uuid.UUID,
        habit_id: uuid.UUID,
    ) -> Habit | None:
        """Archive a habit, scoped by user_id."""
        ...


class NoteRepositoryPort(Protocol):
    """Repository port interface for voice note storage and full-text search."""

    async def create_note(
        self,
        user_id: uuid.UUID,
        content: str,
        tags: list[str] | None = None,
    ) -> Note:
        """Persist a new voice note."""
        ...

    async def get_note(self, user_id: uuid.UUID, note_id: uuid.UUID) -> Note | None:
        """Retrieve note by ID, scoped by user_id."""
        ...

    async def get_latest_note(self, user_id: uuid.UUID) -> Note | None:
        """Retrieve most recently created note for user."""
        ...

    async def search_notes(
        self,
        user_id: uuid.UUID,
        query: str,
        limit: int = 5,
    ) -> list[Note]:
        """Search notes using full-text search and partial matching, scoped by user_id."""
        ...

    async def delete_note(self, user_id: uuid.UUID, note_id: uuid.UUID) -> bool:
        """Delete note by ID, scoped by user_id."""
        ...


class FocusSessionRepositoryPort(Protocol):
    """Repository port interface for focus timer sessions."""

    async def create_session(
        self,
        user_id: uuid.UUID,
        duration_minutes: int,
        started_at: datetime,
        planned_end_at: datetime,
        task_label: str | None = None,
    ) -> FocusSession:
        """Create and persist a new focus session."""
        ...

    async def get_active_session(self, user_id: uuid.UUID) -> FocusSession | None:
        """Get currently active focus session for user, if any."""
        ...

    async def update_session_status(
        self,
        session_id: uuid.UUID,
        status: str,
        actual_end_at: datetime | None = None,
    ) -> FocusSession | None:
        """Update session status and optional actual completion timestamp."""
        ...

    async def list_sessions(
        self,
        user_id: uuid.UUID,
        limit: int = 10,
    ) -> list[FocusSession]:
        """List recent focus sessions for user."""
        ...

    async def get_session_stats(
        self,
        user_id: uuid.UUID,
        since_today: datetime,
    ) -> tuple[int, int, int]:
        """Get (total_completed, total_minutes_focused, today_completed)."""
        ...


class AcademicsAPIPort(Protocol):
    """Structural protocol for invoking Academics cross-module API without AST import."""

    async def get_streak(self, user_id: str | uuid.UUID, timezone_str: str = "UTC") -> int:
        """Return the current consecutive daily study streak count for a user."""
        ...

    async def get_due_flashcard_count(
        self, user_id: str | uuid.UUID, before: datetime | None = None
    ) -> int:
        """Return count of due flashcards for a user on or before the given timestamp."""
        ...

    async def get_today_study_tasks(
        self, user_id: str | uuid.UUID, timezone_str: str = "UTC"
    ) -> list[str]:
        """Return list of today's study plan task topics for user."""
        ...
