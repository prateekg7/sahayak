"""The 'pantry_recipes' MCP tool for pantry tracking, recipe suggestions, and meal planning.

(T9.3).
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from sahayak.core.auth.principal import get_current_principal, requires
from sahayak.core.envelope import fail, ok
from sahayak.core.errors import AuthRequiredError, InvalidInputError, SahayakError
from sahayak.core.idempotency import idempotent
from sahayak.core.observability.instrumentation import instrument_tool
from sahayak.modules.home.schemas import PantryRecipeRequest
from sahayak.modules.home.service.pantry import PantryService

logger = logging.getLogger(__name__)

_pantry_service: PantryService | None = None


def set_pantry_service(service: PantryService) -> None:
    """Inject the active PantryService instance."""
    global _pantry_service
    _pantry_service = service


def get_pantry_service() -> PantryService:
    """Retrieve the injected PantryService instance."""
    if _pantry_service is None:
        raise RuntimeError("PantryService has not been initialized.")
    return _pantry_service


PANTRY_RECIPES_DESCRIPTION = (
    "Manage household pantry ingredients, view expiring items, get recipe suggestions, and "
    "generate meal plans. "
    "Use when the user says 'What can I cook with what is in the pantry?', 'Add olive oil to "
    "the pantry', 'What ingredients are expiring soon?', or 'Suggest a dinner recipe using our "
    "vegetables'. "
    "Do not use for shopping lists; use shared_list instead."
)


@requires()
@idempotent(tool_name="pantry_recipes")
@instrument_tool("pantry_recipes", "home")
async def pantry_recipes(
    action: str = "pantry_list",
    household_id: str | None = None,
    item: str | None = None,
    quantity: str | None = None,
    expires_in_days: int | None = None,
    expires_at: str | None = None,
    diet: str | None = None,
    allergies: list[str] | None = None,
    days: int = 3,
    add_missing_to_shopping_list: bool = False,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Execute pantry operations: add, list, suggest_recipes, meal_plan, preferences."""
    principal = get_current_principal()
    if principal is None or principal.anonymous or principal.user_id is None:
        raise AuthRequiredError(
            spoken=(
                "Please link your account in the Alexa app to view your pantry "
                "and get recipe suggestions."
            ),
            detail="Account linking required for pantry_recipes tool",
        )

    try:
        try:
            req = PantryRecipeRequest(
                action=action.strip().lower(),  # type: ignore[arg-type]
                household_id=household_id,
                item=item,
                quantity=quantity,
                expires_in_days=expires_in_days,
                expires_at=expires_at,
                diet=diet,
                allergies=allergies,
                days=days,
                add_missing_to_shopping_list=add_missing_to_shopping_list,
            )
        except (ValidationError, ValueError) as val_err:
            raise InvalidInputError(
                spoken=(
                    "Please choose a valid action: pantry_add, pantry_list, "
                    "suggest_recipes, meal_plan, or set_preferences."
                ),
                detail=str(val_err),
            ) from val_err

        service = get_pantry_service()

        if req.action == "pantry_add":
            if not req.item:
                raise InvalidInputError("Please specify an ingredient to add to your pantry.")
            data, spoken, next_actions = await service.add_item(
                user_id=principal.user_id,
                household_id_str=req.household_id,
                item=req.item,
                quantity=req.quantity,
                expires_in_days=req.expires_in_days,
                expires_at=req.expires_at,
            )
        elif req.action == "pantry_list":
            data, spoken, next_actions = await service.list_items(
                user_id=principal.user_id,
                household_id_str=req.household_id,
            )
        elif req.action == "suggest_recipes":
            data, spoken, next_actions = await service.suggest_recipes(
                user_id=principal.user_id,
                household_id_str=req.household_id,
                add_missing_to_shopping_list=req.add_missing_to_shopping_list,
            )
        elif req.action == "meal_plan":
            data, spoken, next_actions = await service.meal_plan(
                user_id=principal.user_id,
                household_id_str=req.household_id,
                days=req.days,
            )
        elif req.action == "set_preferences":
            data, spoken, next_actions = await service.set_preferences(
                user_id=principal.user_id,
                household_id_str=req.household_id,
                diet=req.diet,
                allergies=req.allergies,
            )
        else:
            raise InvalidInputError(
                f"Unknown action '{req.action}'. Expected pantry_add, pantry_list, "
                "suggest_recipes, meal_plan, or set_preferences."
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
        logger.exception("Unexpected error in pantry_recipes tool: %s", exc)
        return fail(SahayakError(), module="home", version="0.1.0")
