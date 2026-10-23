"""The 'tasks' MCP tool for personal task and to-do management (T5.1)."""

from __future__ import annotations

import logging
from typing import Any

from sahayak.core.auth.principal import get_current_principal, requires
from sahayak.core.envelope import fail, ok
from sahayak.core.errors import AuthRequiredError, InvalidInputError, SahayakError
from sahayak.core.idempotency import idempotent
from sahayak.core.observability.instrumentation import instrument_tool
from sahayak.modules.productivity.schemas import TaskAction, TasksRequest
from sahayak.modules.productivity.service.tasks import TaskService

logger = logging.getLogger(__name__)

_task_service: TaskService | None = None


def set_task_service(service: TaskService) -> None:
    """Inject the active TaskService instance."""
    global _task_service
    _task_service = service


def get_task_service() -> TaskService:
    """Retrieve the injected TaskService instance."""
    if _task_service is None:
        raise RuntimeError("TaskService has not been initialized.")
    return _task_service


TASKS_DESCRIPTION = (
    "Manage your personal to-do list, create tasks with natural due dates, and mark "
    "items complete. Use when the user says 'Add a task: submit report by Friday', "
    "'What's on my list?', 'Mark task done', or 'Reschedule task'. "
    "Do not use for habits or daily streaks; use the habits tool instead."
)


@requires()
@idempotent(tool_name="tasks")
@instrument_tool("tasks", "productivity")
async def tasks(
    action: str,
    title: str | None = None,
    task_id: str | None = None,
    due_date: str | None = None,
    priority: str = "medium",
    list_name: str = "inbox",
    status: str | None = None,
    tags: list[str] | None = None,
    limit: int = 5,
    timezone: str = "UTC",
    request_id: str | None = None,
) -> dict[str, Any]:
    """Execute task management operations (create, list, complete, reschedule, delete)."""
    principal = get_current_principal()
    if principal is None or principal.anonymous or principal.user_id is None:
        raise AuthRequiredError(
            spoken="Please link your account in the Alexa app to manage personal tasks.",
            detail="Account linking required for tasks tool",
        )

    try:
        req = TasksRequest(
            action=TaskAction(action.strip().lower()),
            title=title,
            task_id=task_id,
            due_date=due_date,
            priority=priority,
            list_name=list_name,
            status=status,
            tags=tags or [],
            limit=limit,
            timezone=timezone,
            request_id=request_id,
        )

        service = get_task_service()

        if req.action == TaskAction.CREATE:
            spoken, data, next_actions = await service.create_task(
                user_id=principal.user_id,
                title=req.title,
                due_date_str=req.due_date,
                priority=req.priority,
                list_name=req.list_name,
                tags=req.tags,
                timezone_str=req.timezone,
            )
        elif req.action == TaskAction.LIST:
            spoken, data, next_actions = await service.list_tasks(
                user_id=principal.user_id,
                status=req.status or "pending",
                list_name=req.list_name if req.list_name != "inbox" else None,
                limit=req.limit,
                timezone_str=req.timezone,
            )
        elif req.action == TaskAction.COMPLETE:
            spoken, data, next_actions = await service.complete_task(
                user_id=principal.user_id,
                task_id_str=req.task_id,
            )
        elif req.action == TaskAction.RESCHEDULE:
            spoken, data, next_actions = await service.reschedule_task(
                user_id=principal.user_id,
                task_id_str=req.task_id,
                due_date_str=req.due_date,
                timezone_str=req.timezone,
            )
        elif req.action == TaskAction.DELETE:
            spoken, data, next_actions = await service.delete_task(
                user_id=principal.user_id,
                task_id_str=req.task_id,
            )
        else:
            raise InvalidInputError(
                spoken=f"Unsupported action {req.action}.",
                detail=f"Unsupported task action '{req.action}'",
            )

        return ok(
            spoken_summary=spoken,
            data=data.model_dump(),
            next_actions=next_actions,
            module="productivity",
            version="0.1.0",
        )
    except SahayakError as err:
        return fail(err, module="productivity", version="0.1.0")
    except Exception as exc:
        logger.exception("Unexpected error in tasks tool: %s", exc)
        return fail(SahayakError(), module="productivity", version="0.1.0")
