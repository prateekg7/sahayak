"""Service orchestrating pantry inventory, recipe suggestions, and meal planning (T9.3)."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

from sahayak.core.db.session import UnitOfWork
from sahayak.core.errors import InvalidInputError, NotFoundError
from sahayak.modules.home.adapters.households import SQLAlchemyHouseholdRepository
from sahayak.modules.home.adapters.pantry import SQLAlchemyPantryRepository
from sahayak.modules.home.domain.pantry import (
    format_meal_plan_spoken,
    format_pantry_added_spoken,
    format_pantry_list_spoken,
    format_recipe_suggestion_spoken,
    is_expiring_soon,
    match_recipes_from_pantry,
    parse_pantry_item,
)
from sahayak.modules.home.service.lists import SharedListService


class PantryService:
    """Service managing pantry ingredients, recipes, and dietary preferences."""

    def __init__(self, session_factory: Any, list_service: SharedListService | None = None) -> None:
        self.session_factory = session_factory
        self.list_service = list_service or SharedListService(session_factory=session_factory)

    async def _resolve_household_id(
        self,
        *,
        user_id: uuid.UUID,
        household_id_str: str | None,
        uow: UnitOfWork,
    ) -> uuid.UUID:
        """Resolve target household ID or auto-create default 'Family' household."""
        h_repo = SQLAlchemyHouseholdRepository(uow.session)

        if household_id_str and household_id_str.strip():
            try:
                h_id = uuid.UUID(household_id_str.strip())
            except ValueError as err:
                raise InvalidInputError("Invalid household ID format.") from err

            membership = await h_repo.get_membership(household_id=h_id, user_id=user_id)
            if not membership:
                raise NotFoundError(
                    spoken="You do not have access to that household.",
                    detail=f"User {user_id} is not a member of {h_id}",
                )
            return h_id

        households = await h_repo.list_user_households(user_id=user_id)
        if not households:
            new_h, _ = await h_repo.create_household(name="Family", created_by=user_id)
            return new_h.id
        return households[0][0].id

    async def add_item(
        self,
        *,
        user_id: uuid.UUID,
        household_id_str: str | None = None,
        item: str,
        quantity: str | None = None,
        expires_in_days: int | None = None,
        expires_at: str | None = None,
    ) -> tuple[dict[str, Any], str, list[str]]:
        """Add or update an ingredient in the pantry inventory."""
        if not item or not item.strip():
            raise InvalidInputError("Please specify an ingredient to add to your pantry.")

        parsed_name, parsed_qty = parse_pantry_item(item, quantity)

        exp_date: date | None = None
        if expires_in_days is not None:
            exp_date = date.today() + timedelta(days=expires_in_days)
        elif expires_at and expires_at.strip():
            try:
                exp_date = date.fromisoformat(expires_at.strip())
            except ValueError as err:
                raise InvalidInputError("Invalid expiration date format. Use YYYY-MM-DD.") from err

        async with UnitOfWork(self.session_factory) as uow:
            h_id = await self._resolve_household_id(
                user_id=user_id,
                household_id_str=household_id_str,
                uow=uow,
            )
            pantry_repo = SQLAlchemyPantryRepository(uow.session)
            p_item = await pantry_repo.add_or_update_item(
                household_id=h_id,
                item_name=parsed_name,
                quantity=parsed_qty,
                expires_at=exp_date,
                added_by=user_id,
            )
            item_dict = p_item.to_dict()
            await uow.session.commit()

        spoken = format_pantry_added_spoken(parsed_name, parsed_qty, exp_date)
        data = {
            "household_id": str(h_id),
            "item": item_dict,
        }
        next_actions = [
            f"pantry_recipes(action='suggest_recipes', household_id='{h_id}')",
            "pantry_recipes(action='pantry_list')",
        ]
        return data, spoken, next_actions

    async def list_items(
        self,
        *,
        user_id: uuid.UUID,
        household_id_str: str | None = None,
    ) -> tuple[dict[str, Any], str, list[str]]:
        """List current pantry inventory and flag expiring ingredients."""
        async with UnitOfWork(self.session_factory) as uow:
            h_id = await self._resolve_household_id(
                user_id=user_id,
                household_id_str=household_id_str,
                uow=uow,
            )
            pantry_repo = SQLAlchemyPantryRepository(uow.session)
            items = await pantry_repo.list_items(household_id=h_id)
            items_dicts = [it.to_dict() for it in items]

        today = date.today()
        expiring = [it for it in items if is_expiring_soon(it.expires_at, today)]
        expiring_dicts = [it.to_dict() for it in expiring]

        spoken = format_pantry_list_spoken(items_dicts, len(expiring_dicts))
        data = {
            "household_id": str(h_id),
            "items": items_dicts,
            "total_items": len(items_dicts),
            "expiring_soon": expiring_dicts,
            "expiring_soon_count": len(expiring_dicts),
        }
        next_actions = [
            "pantry_recipes(action='suggest_recipes')",
            "pantry_recipes(action='pantry_add', item='...')",
        ]
        return data, spoken, next_actions

    async def suggest_recipes(
        self,
        *,
        user_id: uuid.UUID,
        household_id_str: str | None = None,
        add_missing_to_shopping_list: bool = False,
    ) -> tuple[dict[str, Any], str, list[str]]:
        """Suggest recipes based on current pantry items and dietary preferences."""
        async with UnitOfWork(self.session_factory) as uow:
            h_id = await self._resolve_household_id(
                user_id=user_id,
                household_id_str=household_id_str,
                uow=uow,
            )
            pantry_repo = SQLAlchemyPantryRepository(uow.session)
            items = await pantry_repo.list_items(household_id=h_id)
            pref = await pantry_repo.get_or_create_preferences(household_id=h_id)
            diet = pref.diet
            allergies = list(pref.allergies)

        item_names = [it.item_name for it in items]
        recipes = match_recipes_from_pantry(pantry_items=item_names, diet=diet, allergies=allergies)

        if not recipes:
            spoken = "No matching recipes found with your current pantry items."
            data: dict[str, Any] = {
                "household_id": str(h_id),
                "recipes": [],
                "diet": diet,
                "allergies": allergies,
            }
            return data, spoken, ["pantry_recipes(action='pantry_add', item='...')"]

        top_recipe = recipes[0]
        spoken = format_recipe_suggestion_spoken(
            top_recipe.title,
            top_recipe.cooking_time_minutes,
            top_recipe.missing_ingredients,
        )

        # Hand off missing ingredients to shared shopping list if requested
        added_to_list: list[str] = []
        if add_missing_to_shopping_list and top_recipe.missing_ingredients:
            for missing_item in top_recipe.missing_ingredients:
                await self.list_service.add_item(
                    user_id=user_id,
                    household_id_str=str(h_id),
                    list_name="shopping",
                    item=missing_item,
                )
                added_to_list.append(missing_item)

        data = {
            "household_id": str(h_id),
            "recipes": [r.model_dump() for r in recipes],
            "top_recipe": top_recipe.model_dump(),
            "added_to_shopping_list": added_to_list,
        }
        next_actions = [
            "shared_list(action='read', list_name='shopping')",
            "pantry_recipes(action='meal_plan', days=3)",
        ]
        return data, spoken, next_actions

    async def meal_plan(
        self,
        *,
        user_id: uuid.UUID,
        household_id_str: str | None = None,
        days: int = 3,
    ) -> tuple[dict[str, Any], str, list[str]]:
        """Generate a simple multi-day meal plan based on pantry ingredients."""
        clamped_days = max(1, min(days, 7))
        async with UnitOfWork(self.session_factory) as uow:
            h_id = await self._resolve_household_id(
                user_id=user_id,
                household_id_str=household_id_str,
                uow=uow,
            )
            pantry_repo = SQLAlchemyPantryRepository(uow.session)
            items = await pantry_repo.list_items(household_id=h_id)
            pref = await pantry_repo.get_or_create_preferences(household_id=h_id)
            diet = pref.diet
            allergies = list(pref.allergies)

        item_names = [it.item_name for it in items]
        recipes = match_recipes_from_pantry(pantry_items=item_names, diet=diet, allergies=allergies)

        day_names = ["Day 1", "Day 2", "Day 3", "Day 4", "Day 5", "Day 6", "Day 7"]
        plan_entries: list[dict[str, Any]] = []
        for i in range(clamped_days):
            recipe = recipes[i % len(recipes)] if recipes else None
            plan_entries.append(
                {
                    "day": day_names[i],
                    "recipe": recipe.model_dump() if recipe else None,
                    "title": recipe.title if recipe else "Chef's Choice",
                }
            )

        spoken_titles = [p["title"] for p in plan_entries]
        spoken = format_meal_plan_spoken(clamped_days, spoken_titles)
        data = {
            "household_id": str(h_id),
            "days": clamped_days,
            "plan": plan_entries,
        }
        next_actions = ["pantry_recipes(action='suggest_recipes')"]
        return data, spoken, next_actions

    async def set_preferences(
        self,
        *,
        user_id: uuid.UUID,
        household_id_str: str | None = None,
        diet: str | None = None,
        allergies: list[str] | None = None,
    ) -> tuple[dict[str, Any], str, list[str]]:
        """Set or update household dietary preferences and allergies."""
        clean_diet = (diet or "any").strip().lower()
        clean_allergies = [a.strip().lower() for a in (allergies or []) if a and a.strip()]

        async with UnitOfWork(self.session_factory) as uow:
            h_id = await self._resolve_household_id(
                user_id=user_id,
                household_id_str=household_id_str,
                uow=uow,
            )
            pantry_repo = SQLAlchemyPantryRepository(uow.session)
            pref = await pantry_repo.update_preferences(
                household_id=h_id,
                diet=clean_diet,
                allergies=clean_allergies,
            )
            pref_dict = pref.to_dict()
            await uow.session.commit()

        spoken = f"Updated household preferences: diet set to {clean_diet}."
        data = {
            "household_id": str(h_id),
            "preferences": pref_dict,
        }
        next_actions = ["pantry_recipes(action='suggest_recipes')"]
        return data, spoken, next_actions
