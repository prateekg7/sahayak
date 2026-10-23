"""Shared list domain logic: item and quantity parsing, normalization, and speech (T9.2)."""

from __future__ import annotations

import re
from typing import Any

from sahayak.core.errors import InvalidInputError
from sahayak.modules.home.domain.households import sanitize_spoken_text

# Regex pattern to match leading quantities: e.g. "2 liters of milk", "1 kg apples", "3 bananas"
QUANTITY_PATTERN = re.compile(
    r"^(\d+(?:\.\d+)?\s*(?:liters?|litres?|l|kg|kilos?|kilograms?|g|grams?|"
    r"pounds?|lbs?|oz|ounces?|packs?|packets?|boxes?|bottles?|cans?|bunches?|"
    r"dozens?|pieces?|pcs?|cups?|tbsp|tsp)?|\d+)\s*(?:of\s+)?(.+)$",
    re.IGNORECASE,
)


def normalize_list_name(name: str | None) -> str:
    """Normalize list name, defaulting to 'shopping'."""
    if not name or not name.strip():
        return "shopping"
    cleaned = re.sub(r"[^a-zA-Z0-9_\-\s]", "", name).strip().lower()
    cleaned = re.sub(r"\s+", "-", cleaned)
    if not cleaned:
        return "shopping"
    if len(cleaned) > 128:
        raise InvalidInputError("List name cannot exceed 128 characters.")
    return cleaned


def normalize_item_name(item: str) -> str:
    """Normalize item name for storage and deduplication."""
    cleaned = item.strip()
    if not cleaned:
        raise InvalidInputError("Item name cannot be empty.")
    if len(cleaned) > 128:
        raise InvalidInputError("Item name cannot exceed 128 characters.")
    return cleaned.title()


def parse_item_and_quantity(
    raw_item: str,
    explicit_quantity: str | None = None,
) -> tuple[str, str | None]:
    """Extract item name and quantity from input text."""
    cleaned = raw_item.strip()
    if not cleaned:
        raise InvalidInputError("Please specify an item.")

    if explicit_quantity and explicit_quantity.strip():
        return normalize_item_name(cleaned), explicit_quantity.strip()

    match = QUANTITY_PATTERN.match(cleaned)
    if match:
        qty_part, item_part = match.group(1).strip(), match.group(2).strip()
        if item_part:
            return normalize_item_name(item_part), qty_part

    return normalize_item_name(cleaned), None


def format_added_spoken(item: str, quantity: str | None, list_name: str) -> str:
    """Format voice response when an item is added."""
    disp_item = (
        f"{quantity} of {item}"
        if quantity and not quantity.isdigit()
        else (f"{quantity} {item}" if quantity else item)
    )
    clean_list = list_name.replace("-", " ")
    return sanitize_spoken_text(f"Added {disp_item} to your {clean_list} list.")


def format_checked_off_spoken(item: str, list_name: str) -> str:
    """Format voice response when an item is checked off."""
    clean_list = list_name.replace("-", " ")
    return sanitize_spoken_text(f"Checked off {item} on your {clean_list} list.")


def format_removed_spoken(item: str, list_name: str) -> str:
    """Format voice response when an item is removed."""
    clean_list = list_name.replace("-", " ")
    return sanitize_spoken_text(f"Removed {item} from your {clean_list} list.")


def format_cleared_spoken(count: int, list_name: str) -> str:
    """Format voice response when checked items are cleared."""
    suffix = "s" if count != 1 else ""
    clean_list = list_name.replace("-", " ")
    return sanitize_spoken_text(
        f"Cleared {count} checked item{suffix} from your {clean_list} list."
    )


def format_list_items_spoken(list_name: str, items: list[dict[str, Any]]) -> str:
    """Format voice summary of list items."""
    clean_list = list_name.replace("-", " ")
    unchecked = [it for it in items if not it.get("checked", False)]
    if not unchecked:
        return sanitize_spoken_text(f"Your {clean_list} list is currently empty.")

    count = len(unchecked)
    names = []
    for it in unchecked[:5]:
        qty = it.get("quantity")
        name = it.get("item_name", "")
        names.append(f"{qty} {name}" if qty else name)

    if count == 1:
        summary_items = names[0]
    elif count == 2:
        summary_items = f"{names[0]} and {names[1]}"
    else:
        summary_items = ", ".join(names[:-1]) + f", and {names[-1]}"

    more = f" and {count - 5} more" if count > 5 else ""
    suffix = "s" if count != 1 else ""
    return sanitize_spoken_text(
        f"Your {clean_list} list has {count} item{suffix}: {summary_items}{more}."
    )
