"""Domain logic for pantry inventory, recipe validation, and meal planning (T9.3)."""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

from pydantic import BaseModel, Field

from sahayak.core.errors import InvalidInputError
from sahayak.modules.home.domain.households import sanitize_spoken_text
from sahayak.modules.home.domain.lists import QUANTITY_PATTERN, normalize_item_name

BASIC_STAPLES = {
    "salt",
    "black pepper",
    "pepper",
    "water",
    "cooking oil",
    "olive oil",
    "vegetable oil",
    "oil",
    "sugar",
    "flour",
}

NON_VEG_KEYWORDS = {
    "chicken",
    "beef",
    "pork",
    "meat",
    "fish",
    "shrimp",
    "lamb",
    "bacon",
    "salmon",
    "tuna",
    "turkey",
    "seafood",
}

NON_VEGAN_KEYWORDS = NON_VEG_KEYWORDS | {
    "milk",
    "cheese",
    "butter",
    "egg",
    "eggs",
    "cream",
    "yogurt",
    "honey",
    "ghee",
}


class Recipe(BaseModel):
    """Structured recipe suggestion."""

    title: str = Field(..., max_length=128)
    description: str = Field(..., max_length=256)
    used_ingredients: list[str] = Field(default_factory=list)
    missing_ingredients: list[str] = Field(default_factory=list)
    cooking_time_minutes: int = Field(default=20, ge=1, le=240)
    instructions: list[str] = Field(default_factory=list)


def parse_pantry_item(
    raw_item: str,
    explicit_quantity: str | None = None,
) -> tuple[str, str | None]:
    """Parse item name and quantity."""
    cleaned = raw_item.strip()
    if not cleaned:
        raise InvalidInputError("Please specify a pantry item.")

    if explicit_quantity and explicit_quantity.strip():
        return normalize_item_name(cleaned), explicit_quantity.strip()

    match = QUANTITY_PATTERN.match(cleaned)
    if match:
        qty_part, item_part = match.group(1).strip(), match.group(2).strip()
        if item_part:
            return normalize_item_name(item_part), qty_part

    return normalize_item_name(cleaned), None


def is_expiring_soon(
    expires_at: date | None,
    today: date | None = None,
    days_threshold: int = 3,
) -> bool:
    """Return True if item expires within the threshold days."""
    if expires_at is None:
        return False
    ref_date = today or date.today()
    return ref_date <= expires_at <= (ref_date + timedelta(days=days_threshold))


def check_diet_compliance(ingredients: list[str], diet: str) -> bool:
    """Return True if all ingredients comply with the specified dietary restriction."""
    clean_diet = diet.strip().lower()
    if clean_diet in {"any", "none", ""}:
        return True

    words = {word.lower() for ing in ingredients for word in re.findall(r"\w+", ing)}
    if clean_diet == "vegetarian":
        return not bool(words & NON_VEG_KEYWORDS)
    if clean_diet == "vegan":
        return not bool(words & NON_VEGAN_KEYWORDS)
    return True


def check_allergen_free(ingredients: list[str], allergies: list[str]) -> bool:
    """Return True if none of the ingredients contain declared allergens."""
    if not allergies:
        return True

    lower_allergens = {a.strip().lower() for a in allergies if a and a.strip()}
    for ing in ingredients:
        ing_lower = ing.lower()
        for allergen in lower_allergens:
            if allergen in ing_lower:
                return False
    return True


# Curated catalog of flexible home recipes
CURATED_RECIPES = [
    {
        "title": "Classic Scrambled Eggs",
        "description": "Fluffy scrambled eggs with butter and black pepper.",
        "ingredients": ["Eggs", "Butter", "Black Pepper", "Salt"],
        "cooking_time_minutes": 10,
        "instructions": [
            "Beat eggs with salt and pepper in a bowl.",
            "Melt butter in a skillet over medium-low heat.",
            "Pour in eggs and stir gently until soft curds form.",
        ],
    },
    {
        "title": "Garlic Olive Oil Pasta",
        "description": "Quick Italian pasta tossed with sautéed garlic and olive oil.",
        "ingredients": ["Pasta", "Garlic", "Olive Oil", "Salt", "Black Pepper"],
        "cooking_time_minutes": 15,
        "instructions": [
            "Boil pasta in salted water until al dente.",
            "Gently warm sliced garlic in olive oil in a pan.",
            "Toss drained pasta with garlic oil and season with pepper.",
        ],
    },
    {
        "title": "Vegetable Fried Rice",
        "description": "Savory fried rice loaded with crisp vegetables.",
        "ingredients": ["Rice", "Onion", "Carrots", "Cooking Oil", "Soy Sauce", "Salt"],
        "cooking_time_minutes": 20,
        "instructions": [
            "Heat oil in a wok and sauté diced onions and carrots.",
            "Add cooked rice and break up any clumps over high heat.",
            "Stir in soy sauce and toss until well combined.",
        ],
    },
    {
        "title": "Comforting Lentil Soup",
        "description": "Hearty spiced lentil dahl soup.",
        "ingredients": ["Lentils", "Onion", "Tomato", "Garlic", "Cooking Oil", "Salt"],
        "cooking_time_minutes": 25,
        "instructions": [
            "Rinse lentils and simmer in water until tender.",
            "In a small pan, fry chopped onions, garlic, and tomatoes in oil.",
            "Combine fried aromatics into the lentils and simmer for 5 minutes.",
        ],
    },
    {
        "title": "Warm Honey Oatmeal",
        "description": "Hearty rolled oats sweetened with honey and cinnamon.",
        "ingredients": ["Oats", "Milk", "Honey", "Salt"],
        "cooking_time_minutes": 10,
        "instructions": [
            "Bring milk and a pinch of salt to a gentle simmer.",
            "Stir in oats and cook for 5 minutes until creamy.",
            "Drizzle with honey before serving warm.",
        ],
    },
]


def match_recipes_from_pantry(
    pantry_items: list[str],
    diet: str = "any",
    allergies: list[str] | None = None,
) -> list[Recipe]:
    """Find recipes matching available pantry items and dietary preferences."""
    allergies_list = allergies or []
    pantry_set = {it.lower() for it in pantry_items}

    matched: list[Recipe] = []
    for r in CURATED_RECIPES:
        raw_ings = r.get("ingredients", [])
        recipe_ings: list[str] = [str(x) for x in raw_ings] if isinstance(raw_ings, list) else []
        if not check_diet_compliance(recipe_ings, diet):
            continue
        if not check_allergen_free(recipe_ings, allergies_list):
            continue

        used: list[str] = []
        missing: list[str] = []
        for ing in recipe_ings:
            ing_lower = ing.lower()
            staple = ing_lower in BASIC_STAPLES
            in_pantry = any(p in ing_lower or ing_lower in p for p in pantry_set)
            if in_pantry or staple:
                used.append(ing)
            else:
                missing.append(ing)

        # Include if at least one ingredient is in the pantry
        if used and len(used) >= len(missing):
            matched.append(
                Recipe(
                    title=r["title"],  # type: ignore[arg-type]
                    description=r["description"],  # type: ignore[arg-type]
                    used_ingredients=used,
                    missing_ingredients=missing,
                    cooking_time_minutes=r["cooking_time_minutes"],  # type: ignore[arg-type]
                    instructions=r["instructions"],  # type: ignore[arg-type]
                )
            )

    return matched


def format_pantry_added_spoken(
    item: str,
    quantity: str | None,
    expires_at: date | None,
) -> str:
    """Voice summary when a pantry item is added."""
    disp_item = (
        f"{quantity} of {item}"
        if quantity and not quantity.isdigit()
        else (f"{quantity} {item}" if quantity else item)
    )
    exp_part = f" expiring on {expires_at.strftime('%B %d')}" if expires_at else ""
    return sanitize_spoken_text(f"Added {disp_item} to your pantry{exp_part}.")


def format_pantry_list_spoken(
    items: list[dict[str, Any]],
    expiring_soon_count: int = 0,
) -> str:
    """Voice summary of current pantry contents."""
    if not items:
        return sanitize_spoken_text("Your pantry is currently empty.")

    count = len(items)
    names: list[str] = []
    for it in items[:4]:
        name = it.get("item_name", "")
        qty = it.get("quantity")
        names.append(f"{qty} {name}" if qty else name)

    summary = ", ".join(names)
    more = f" and {count - 4} more" if count > 4 else ""
    suffix = "s" if count != 1 else ""
    alert = (
        f" Note: {expiring_soon_count} item{'s' if expiring_soon_count != 1 else ''} expiring soon."
        if expiring_soon_count > 0
        else ""
    )
    return sanitize_spoken_text(f"Your pantry has {count} item{suffix}: {summary}{more}.{alert}")


def format_recipe_suggestion_spoken(
    recipe_title: str,
    cooking_time_min: int,
    missing: list[str],
) -> str:
    """Voice summary when suggesting a recipe."""
    if missing:
        missing_str = ", ".join(missing[:3])
        return sanitize_spoken_text(
            f"You can make {recipe_title} in {cooking_time_min} minutes. "
            f"You just need to get {missing_str}."
        )
    return sanitize_spoken_text(
        f"You have all ingredients to make {recipe_title} in {cooking_time_min} minutes."
    )


def format_meal_plan_spoken(days: int, meal_titles: list[str]) -> str:
    """Voice summary for a meal plan."""
    if not meal_titles:
        return sanitize_spoken_text("Could not generate a meal plan from current pantry items.")

    plan_str = ", ".join(meal_titles[:days])
    return sanitize_spoken_text(
        f"Here is your {days} day dinner plan using your pantry: {plan_str}."
    )
