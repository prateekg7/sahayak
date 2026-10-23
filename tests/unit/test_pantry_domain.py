"""Unit tests for pantry and recipe domain logic (T9.3)."""

from __future__ import annotations

from datetime import date

import pytest

from sahayak.core.errors import InvalidInputError
from sahayak.modules.home.domain.pantry import (
    check_allergen_free,
    check_diet_compliance,
    format_meal_plan_spoken,
    format_pantry_added_spoken,
    format_pantry_list_spoken,
    format_recipe_suggestion_spoken,
    is_expiring_soon,
    match_recipes_from_pantry,
    parse_pantry_item,
)


def test_parse_pantry_item() -> None:
    name, qty = parse_pantry_item("2 kg basmati rice")
    assert name == "Basmati Rice"
    assert qty == "2 kg"

    name, qty = parse_pantry_item("olive oil", explicit_quantity="500 ml")
    assert name == "Olive Oil"
    assert qty == "500 ml"

    name, qty = parse_pantry_item("eggs")
    assert name == "Eggs"
    assert qty is None

    with pytest.raises(InvalidInputError, match="Please specify a pantry item"):
        parse_pantry_item("   ")


def test_is_expiring_soon() -> None:
    today = date(2026, 11, 1)
    assert is_expiring_soon(date(2026, 11, 2), today=today, days_threshold=3) is True
    assert is_expiring_soon(date(2026, 11, 4), today=today, days_threshold=3) is True
    assert is_expiring_soon(date(2026, 11, 10), today=today, days_threshold=3) is False
    assert is_expiring_soon(None, today=today) is False


def test_diet_and_allergen_compliance() -> None:
    veg_ingredients = ["Rice", "Carrots", "Cooking Oil", "Salt"]
    non_veg_ingredients = ["Chicken", "Rice", "Salt"]
    dairy_ingredients = ["Pasta", "Milk", "Cheese"]

    assert check_diet_compliance(veg_ingredients, "vegetarian") is True
    assert check_diet_compliance(non_veg_ingredients, "vegetarian") is False

    assert check_diet_compliance(dairy_ingredients, "vegan") is False
    assert check_diet_compliance(veg_ingredients, "vegan") is True

    assert check_allergen_free(dairy_ingredients, ["peanuts"]) is True
    assert check_allergen_free(dairy_ingredients, ["milk"]) is False
    assert check_allergen_free(dairy_ingredients, ["cheese"]) is False


def test_match_recipes_from_pantry() -> None:
    # Pantry with pasta and garlic
    recipes = match_recipes_from_pantry(
        ["pasta", "garlic"],
        diet="vegetarian",
    )
    assert len(recipes) >= 1
    pasta_recipe = next((r for r in recipes if "Pasta" in r.title), None)
    assert pasta_recipe is not None
    assert any("pasta" in ing.lower() for ing in pasta_recipe.used_ingredients)


def test_pantry_spoken_formatters() -> None:
    added = format_pantry_added_spoken("Olive Oil", "500 ml", date(2026, 12, 1))
    assert len(added) <= 300
    assert "Olive Oil" in added and "500 ml" in added

    p_list = format_pantry_list_spoken(
        [
            {"item_name": "Basmati Rice", "quantity": "1 kg", "expires_at": None},
            {"item_name": "Whole Milk", "quantity": "1 liter", "expires_at": "2026-11-02"},
        ],
        expiring_soon_count=1,
    )
    assert len(p_list) <= 300
    assert "pantry" in p_list.lower()

    recipes = match_recipes_from_pantry(["pasta", "garlic"])
    assert len(recipes) > 0
    rec_spoken = format_recipe_suggestion_spoken(
        recipes[0].title,
        recipes[0].cooking_time_minutes,
        recipes[0].missing_ingredients,
    )
    assert len(rec_spoken) <= 300
    assert "*" not in rec_spoken and "`" not in rec_spoken

    meal_plan_spoken = format_meal_plan_spoken(1, [recipes[0].title])
    assert len(meal_plan_spoken) <= 300
