"""The 'application_tracker' MCP tool for tracking job applications (T8.2)."""

from __future__ import annotations

import logging
from typing import Any

from sahayak.core.auth.principal import get_current_principal, requires
from sahayak.core.envelope import fail, ok
from sahayak.core.errors import AuthRequiredError, InvalidInputError, SahayakError
from sahayak.core.idempotency import idempotent
from sahayak.core.observability.instrumentation import instrument_tool
from sahayak.modules.career.schemas import ApplicationRequest
from sahayak.modules.career.service.applications import ApplicationService

logger = logging.getLogger(__name__)

_application_service: ApplicationService | None = None


def set_application_service(service: ApplicationService) -> None:
    """Inject the active ApplicationService instance."""
    global _application_service
    _application_service = service


def get_application_service() -> ApplicationService:
    """Retrieve the injected ApplicationService instance."""
    if _application_service is None:
        raise RuntimeError("ApplicationService has not been initialized.")
    return _application_service


APPLICATION_TRACKER_DESCRIPTION = (
    "Track job applications, interview stages, and follow-up deadlines. "
    "Use when the user says 'Add an application for Google as Software Engineer', "
    "'What is the status of my job applications?', 'Update my Meta application to interviewing', "
    "or 'What follow-ups are due today?'. "
    "Do not use for logging personal tasks, expenses, or health metrics."
)


@requires()
@idempotent(tool_name="application_tracker")
@instrument_tool("application_tracker", "career")
async def application_tracker(
    action: str = "list",
    company: str | None = None,
    role: str | None = None,
    status: str | None = None,
    follow_up_at: str | None = None,
    notes: str | None = None,
    application_id: str | None = None,
    limit: int = 10,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Execute job application operations: add, update_status, list, due_followups, delete."""
    principal = get_current_principal()
    if principal is None or principal.anonymous or principal.user_id is None:
        raise AuthRequiredError(
            spoken=(
                "Please link your account in the Alexa app to track and manage "
                "your job applications."
            ),
            detail="Account linking required for application_tracker tool",
        )

    try:
        req = ApplicationRequest(
            action=action.strip().lower(),  # type: ignore[arg-type]
            company=company,
            role=role,
            status=status,
            follow_up_at=follow_up_at,
            notes=notes,
            application_id=application_id,
            limit=limit,
        )

        service = get_application_service()

        if req.action == "add":
            if not req.company:
                raise InvalidInputError("Company name is required to add an application.")
            if not req.role:
                raise InvalidInputError("Job role is required to add an application.")
            data, spoken, next_actions = await service.add_application(
                user_id=principal.user_id,
                company=req.company,
                role=req.role,
                status=req.status or "applied",
                follow_up_at_str=req.follow_up_at,
                notes=req.notes,
            )
        elif req.action == "update_status":
            if not req.application_id:
                raise InvalidInputError("application_id is required to update status.")
            if not req.status:
                raise InvalidInputError("status is required to update application.")
            data, spoken, next_actions = await service.update_status(
                user_id=principal.user_id,
                application_id_str=req.application_id,
                status=req.status,
                notes=req.notes,
            )
        elif req.action == "list":
            data, spoken, next_actions = await service.list_applications(
                user_id=principal.user_id,
                status=req.status,
                limit=req.limit,
            )
        elif req.action == "due_followups":
            data, spoken, next_actions = await service.list_due_followups(
                user_id=principal.user_id,
                limit=req.limit,
            )
        elif req.action == "delete":
            if not req.application_id:
                raise InvalidInputError("application_id is required to delete an application.")
            data, spoken, next_actions = await service.delete_application(
                user_id=principal.user_id,
                application_id_str=req.application_id,
            )
        else:
            raise InvalidInputError(
                f"Unknown action '{req.action}'. Expected add, update_status, list, "
                "due_followups, or delete."
            )

        return ok(
            spoken_summary=spoken,
            data=data,
            next_actions=next_actions,
            module="career",
            version="0.1.0",
        )
    except SahayakError as err:
        return fail(err, module="career", version="0.1.0")
    except Exception as exc:
        logger.exception("Unexpected error in application_tracker tool: %s", exc)
        return fail(SahayakError(), module="career", version="0.1.0")
