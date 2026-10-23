"""The 'shared_list' MCP tool for shared family shopping and grocery lists (T9.2)."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from sahayak.core.auth.principal import get_current_principal, requires
from sahayak.core.envelope import fail, ok
from sahayak.core.errors import AuthRequiredError, InvalidInputError, SahayakError
from sahayak.core.idempotency import idempotent
from sahayak.core.observability.instrumentation import instrument_tool
from sahayak.modules.home.schemas import SharedListRequest
from sahayak.modules.home.service.lists import SharedListService

logger = logging.getLogger(__name__)

_shared_list_service: SharedListService | None = None


def set_shared_list_service(service: SharedListService) -> None:
    """Inject the active SharedListService instance."""
    global _shared_list_service
    _shared_list_service = service


def get_shared_list_service() -> SharedListService:
    """Retrieve the injected SharedListService instance."""
    if _shared_list_service is None:
        raise RuntimeError("SharedListService has not been initialized.")
    return _shared_list_service


SHARED_LIST_DESCRIPTION = (
    "Add, remove, read, check off, and clear items on shared household lists like groceries. "
    "Use when the user says 'Add milk to the shopping list', 'What is on our grocery list?', "
    "'Check off eggs', or 'Clear finished items from the list'. "
    "Do not use for personal private tasks or habit tracking."
)


@requires()
@idempotent(tool_name="shared_list")
@instrument_tool("shared_list", "home")
async def shared_list(
    action: str = "read",
    household_id: str | None = None,
    list_name: str | None = "shopping",
    item: str | None = None,
    quantity: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Execute shared list operations: add, read, check_off, remove, clear_checked."""
    principal = get_current_principal()
    if principal is None or principal.anonymous or principal.user_id is None:
        raise AuthRequiredError(
            spoken=(
                "Please link your account in the Alexa app to view and manage "
                "your shared household lists."
            ),
            detail="Account linking required for shared_list tool",
        )

    try:
        try:
            req = SharedListRequest(
                action=action.strip().lower(),  # type: ignore[arg-type]
                household_id=household_id,
                list_name=list_name or "shopping",
                item=item,
                quantity=quantity,
            )
        except (ValidationError, ValueError) as val_err:
            raise InvalidInputError(
                spoken=(
                    "Please choose a valid action: add, read, check_off, remove, or clear_checked."
                ),
                detail=str(val_err),
            ) from val_err

        service = get_shared_list_service()

        if req.action == "add":
            if not req.item:
                raise InvalidInputError("Please specify an item to add to the list.")
            data, spoken, next_actions = await service.add_item(
                user_id=principal.user_id,
                household_id_str=req.household_id,
                list_name=req.list_name,
                item=req.item,
                quantity=req.quantity,
            )
        elif req.action == "read":
            data, spoken, next_actions = await service.read_list(
                user_id=principal.user_id,
                household_id_str=req.household_id,
                list_name=req.list_name,
            )
        elif req.action == "check_off":
            if not req.item:
                raise InvalidInputError("Please specify which item to check off.")
            data, spoken, next_actions = await service.check_off_item(
                user_id=principal.user_id,
                household_id_str=req.household_id,
                list_name=req.list_name,
                item=req.item,
            )
        elif req.action == "remove":
            if not req.item:
                raise InvalidInputError("Please specify which item to remove.")
            data, spoken, next_actions = await service.remove_item(
                user_id=principal.user_id,
                household_id_str=req.household_id,
                list_name=req.list_name,
                item=req.item,
            )
        elif req.action == "clear_checked":
            data, spoken, next_actions = await service.clear_checked(
                user_id=principal.user_id,
                household_id_str=req.household_id,
                list_name=req.list_name,
            )
        else:
            raise InvalidInputError(
                f"Unknown action '{req.action}'. Expected add, read, "
                "check_off, remove, or clear_checked."
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
        logger.exception("Unexpected error in shared_list tool: %s", exc)
        return fail(SahayakError(), module="home", version="0.1.0")
