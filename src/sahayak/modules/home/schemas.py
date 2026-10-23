"""Pydantic schemas for the home and family module (T9.2)."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class SharedListAction(StrEnum):
    """Supported operations for the shared_list MCP tool."""

    ADD = "add"
    REMOVE = "remove"
    READ = "read"
    CHECK_OFF = "check_off"
    CLEAR_CHECKED = "clear_checked"


class SharedListRequest(BaseModel):
    """Request model for the shared_list tool."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    action: SharedListAction = SharedListAction.READ
    household_id: str | None = None
    list_name: Annotated[str, Field(default="shopping", max_length=128)] = "shopping"
    item: Annotated[str | None, Field(default=None, max_length=128)] = None
    quantity: Annotated[str | None, Field(default=None, max_length=64)] = None


class ChoreAction(StrEnum):
    """Supported operations for the chores MCP tool."""

    ADD = "add"
    WHOSE_TURN = "whose_turn"
    COMPLETE = "complete"
    ASSIGN = "assign"
    LIST = "list"


class ChoreRequest(BaseModel):
    """Request model for the chores tool."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    action: ChoreAction = ChoreAction.LIST
    household_id: str | None = None
    title: Annotated[str | None, Field(default=None, max_length=256)] = None
    frequency: Annotated[str | None, Field(default="weekly", max_length=32)] = "weekly"
    assigned_to: Annotated[str | None, Field(default=None, max_length=128)] = None
    rotation_members: list[str] | None = None


class PantryRecipeAction(StrEnum):
    """Supported operations for the pantry_recipes MCP tool."""

    PANTRY_ADD = "pantry_add"
    PANTRY_LIST = "pantry_list"
    SUGGEST_RECIPES = "suggest_recipes"
    MEAL_PLAN = "meal_plan"
    SET_PREFERENCES = "set_preferences"


class PantryRecipeRequest(BaseModel):
    """Request model for the pantry_recipes tool."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    action: PantryRecipeAction = PantryRecipeAction.PANTRY_LIST
    household_id: str | None = None
    item: Annotated[str | None, Field(default=None, max_length=128)] = None
    quantity: Annotated[str | None, Field(default=None, max_length=64)] = None
    expires_in_days: Annotated[int | None, Field(default=None, ge=1, le=365)] = None
    expires_at: Annotated[str | None, Field(default=None, max_length=32)] = None
    diet: Annotated[str | None, Field(default=None, max_length=64)] = None
    allergies: list[str] | None = None
    days: Annotated[int, Field(default=3, ge=1, le=14)] = 3
    add_missing_to_shopping_list: bool = False
