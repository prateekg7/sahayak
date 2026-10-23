"""Pydantic schemas for the productivity module (T5.1)."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class TaskAction(str, Enum):
    CREATE = "create"
    LIST = "list"
    COMPLETE = "complete"
    RESCHEDULE = "reschedule"
    DELETE = "delete"


class TasksRequest(BaseModel):
    """Input payload for the 'tasks' MCP tool."""

    action: TaskAction = Field(
        ...,
        description=(
            "The task management action: 'create', 'list', 'complete', 'reschedule', or 'delete'."
        ),
    )
    title: str | None = Field(
        default=None,
        max_length=255,
        description="Task title (required for 'create').",
    )
    task_id: str | None = Field(
        default=None,
        description="Task UUID (required for 'complete', 'reschedule', 'delete').",
    )
    due_date: str | None = Field(
        default=None,
        max_length=100,
        description=(
            "Due date in natural speech (e.g. 'tomorrow', 'Friday', 'in 3 days') or ISO format."
        ),
    )
    priority: str = Field(
        default="medium",
        pattern=r"^(low|medium|high)$",
        description="Priority: 'low', 'medium', or 'high'.",
    )
    list_name: str = Field(
        default="inbox",
        max_length=100,
        description="Target task list (default: 'inbox').",
    )
    status: str | None = Field(
        default=None,
        description="Filter tasks by status ('pending', 'completed') when listing.",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Optional list of string tags for categorization.",
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum number of tasks to return when listing.",
    )
    timezone: str = Field(
        default="UTC",
        description="User's IANA timezone (e.g. 'America/New_York', 'Asia/Kolkata').",
    )
    request_id: str | None = Field(
        default=None,
        description="Optional idempotency key for mutations.",
    )


class TaskData(BaseModel):
    """Representation of an individual task."""

    id: str
    user_id: str
    title: str
    list_name: str
    priority: str
    status: str
    due_at: str | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: str | None = None
    completed_at: str | None = None


class TasksResponseData(BaseModel):
    """Output payload for the 'tasks' tool inside the standard envelope."""

    action: str
    task: TaskData | None = None
    tasks: list[TaskData] = Field(default_factory=list)
    count: int = 0


class HabitAction(str, Enum):
    """Supported habit management actions."""

    CREATE = "create"
    LOG = "log"
    STATUS = "status"
    LIST = "list"


class HabitsRequest(BaseModel):
    """Input payload for the 'habits' MCP tool."""

    action: HabitAction = Field(
        ...,
        description="Habit management action: 'create', 'log', 'status', or 'list'.",
    )
    name: str | None = Field(
        default=None,
        max_length=255,
        description="Habit name (e.g. 'morning meditation', 'read 20 pages').",
    )
    habit_id: str | None = Field(
        default=None,
        description="Optional habit UUID.",
    )
    frequency: str = Field(
        default="daily",
        pattern=r"^(daily|weekly)$",
        description="Target frequency: 'daily' or 'weekly'.",
    )
    date: str | None = Field(
        default=None,
        description="Optional completion date (YYYY-MM-DD), defaults to today.",
    )
    timezone: str = Field(
        default="UTC",
        description="User's IANA timezone (e.g. 'America/New_York', 'Asia/Kolkata').",
    )
    request_id: str | None = Field(
        default=None,
        description="Optional idempotency key for mutations.",
    )


class HabitData(BaseModel):
    """Representation of an individual habit."""

    id: str
    user_id: str
    name: str
    target_frequency: str
    streak_current: int = 0
    streak_longest: int = 0
    last_logged_date: str | None = None
    created_at: str | None = None


class HabitsResponseData(BaseModel):
    """Output payload for the 'habits' tool inside the standard envelope."""

    action: str
    habit: HabitData | None = None
    habits: list[HabitData] = Field(default_factory=list)
    count: int = 0


class NoteAction(str, Enum):
    """Supported voice note actions."""

    ADD = "add"
    SEARCH = "search"
    READ_LATEST = "read_latest"
    DELETE = "delete"


class NotesRequest(BaseModel):
    """Input payload for the 'notes' MCP tool."""

    action: NoteAction = Field(
        ...,
        description="Note management action: 'add', 'search', 'read_latest', or 'delete'.",
    )
    content: str | None = Field(
        default=None,
        max_length=2000,
        description="Note content text (required for 'add').",
    )
    query: str | None = Field(
        default=None,
        max_length=255,
        description="Search query words (required for 'search').",
    )
    note_id: str | None = Field(
        default=None,
        description="Note UUID (required for 'delete').",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Optional categorization tags.",
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum search results to return.",
    )
    request_id: str | None = Field(
        default=None,
        description="Optional idempotency key for mutations.",
    )


class NoteData(BaseModel):
    """Representation of an individual voice note."""

    id: str
    user_id: str
    content: str
    tags: list[str] = Field(default_factory=list)
    created_at: str | None = None


class NotesResponseData(BaseModel):
    """Output payload for the 'notes' tool inside the standard envelope."""

    action: str
    note: NoteData | None = None
    notes: list[NoteData] = Field(default_factory=list)
    count: int = 0
    has_more: bool = False
