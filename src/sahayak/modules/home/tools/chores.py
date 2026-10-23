"""The 'chores' MCP tool for shared household chores and fair rotation (T9.3)."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from sahayak.core.auth.principal import get_current_principal, requires
from sahayak.core.envelope import fail, ok
from sahayak.core.errors import AuthRequiredError, InvalidInputError, SahayakError
from sahayak.core.idempotency import idempotent
from sahayak.core.observability.instrumentation import instrument_tool
from sahayak.modules.home.schemas import ChoreRequest
from sahayak.modules.home.service.chores import ChoreService

logger = logging.getLogger(__name__)

_chore_service: ChoreService | None = None


def set_chore_service(service: ChoreService) -> None:
    """Inject the active ChoreService instance."""
    global _chore_service
    _chore_service = service


def get_chore_service() -> ChoreService:
    """Retrieve the injected ChoreService instance."""
    if _chore_service is None:
        raise RuntimeError("ChoreService has not been initialized.")
    return _chore_service


CHORES_DESCRIPTION = (
    "Assign, track whose turn it is, complete, and list shared household chores with fair "
    "rotation. "
    "Use when the user says 'Whose turn is it to do the dishes?', 'Add take out trash to chores', "
    "'I completed vacuuming the living room', or 'Assign dishes to Alice and Bob'. "
    "Do not use for personal private tasks; use tasks instead."
)


@requires()
@idempotent(tool_name="chores")
@instrument_tool("chores", "home")
async def chores(
    action: str = "list",
    household_id: str | None = None,
    title: str | None = None,
    frequency: str | None = "weekly",
    assigned_to: str | None = None,
    rotation_members: list[str] | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Execute household chore operations: add, whose_turn, complete, assign, list."""
    principal = get_current_principal()
    if principal is None or principal.anonymous or principal.user_id is None:
        raise AuthRequiredError(
            spoken=(
                "Please link your account in the Alexa app to view and manage "
                "your household chores."
            ),
            detail="Account linking required for chores tool",
        )

    try:
        try:
            req = ChoreRequest(
                action=action.strip().lower(),  # type: ignore[arg-type]
                household_id=household_id,
                title=title,
                frequency=frequency,
                assigned_to=assigned_to,
                rotation_members=rotation_members,
            )
        except (ValidationError, ValueError) as val_err:
            raise InvalidInputError(
                spoken=(
                    "Please choose a valid action: add, whose_turn, complete, assign, or list."
                ),
                detail=str(val_err),
            ) from val_err

        service = get_chore_service()

        if req.action == "add":
            if not req.title:
                raise InvalidInputError("Please specify a title for the chore.")
            data, spoken, next_actions = await service.add_chore(
                user_id=principal.user_id,
                household_id_str=req.household_id,
                title=req.title,
                frequency=req.frequency,
                assigned_to=req.assigned_to,
                rotation_members=req.rotation_members,
            )
        elif req.action == "whose_turn":
            data, spoken, next_actions = await service.whose_turn(
                user_id=principal.user_id,
                household_id_str=req.household_id,
                title=req.title,
            )
        elif req.action == "complete":
            if not req.title:
                raise InvalidInputError("Please specify which chore you completed.")
            data, spoken, next_actions = await service.complete_chore(
                user_id=principal.user_id,
                household_id_str=req.household_id,
                title=req.title,
            )
        elif req.action == "assign":
            if not req.title:
                raise InvalidInputError("Please specify which chore to assign.")
            data, spoken, next_actions = await service.assign_chore(
                user_id=principal.user_id,
                household_id_str=req.household_id,
                title=req.title,
                assigned_to=req.assigned_to,
                rotation_members=req.rotation_members,
            )
        elif req.action == "list":
            data, spoken, next_actions = await service.list_chores(
                user_id=principal.user_id,
                household_id_str=req.household_id,
            )
        else:
            raise InvalidInputError(
                f"Unknown action '{req.action}'. Expected add, whose_turn, "
                "complete, assign, or list."
            )

        return ok(
            spoken_summary=spoken,
            data=data,
            next_actions=next_actions,
            module="home",
            version="0.1.0",
        )
    except SahayakError as err:
        return fail(err, module="home", version="0.1.0")
    except Exception as exc:
        logger.exception("Unexpected error in chores tool: %s", exc)
        return fail(SahayakError(), module="home", version="0.1.0")
