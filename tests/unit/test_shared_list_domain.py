"""Unit tests for shared list domain logic (T9.2)."""

from __future__ import annotations

from typing import Any

import pytest

from sahayak.core.errors import InvalidInputError
from sahayak.modules.home.domain.lists import (
    format_added_spoken,
    format_checked_off_spoken,
    format_cleared_spoken,
    format_list_items_spoken,
    format_removed_spoken,
    normalize_item_name,
    normalize_list_name,
    parse_item_and_quantity,
)


def test_normalize_list_name() -> None:
    assert normalize_list_name(None) == "shopping"
    assert normalize_list_name("") == "shopping"
    assert normalize_list_name("   ") == "shopping"
    assert normalize_list_name("Weekly Groceries") == "weekly-groceries"
    assert normalize_list_name("Hardware Store!!!") == "hardware-store"

    long_name = "a" * 129
    with pytest.raises(InvalidInputError):
        normalize_list_name(long_name)


def test_normalize_item_name() -> None:
    assert normalize_item_name("whole milk") == "Whole Milk"
    assert normalize_item_name("  organic eggs  ") == "Organic Eggs"

    with pytest.raises(InvalidInputError):
        normalize_item_name("")

    with pytest.raises(InvalidInputError):
        normalize_item_name("   ")

    with pytest.raises(InvalidInputError):
        normalize_item_name("a" * 129)


def test_parse_item_and_quantity() -> None:
    item, qty = parse_item_and_quantity("2 liters of whole milk")
    assert item == "Whole Milk"
    assert qty == "2 liters"

    item, qty = parse_item_and_quantity("1 kg apples")
    assert item == "Apples"
    assert qty == "1 kg"

    item, qty = parse_item_and_quantity("3 bananas")
    assert item == "Bananas"
    assert qty == "3"

    item, qty = parse_item_and_quantity("salted butter")
    assert item == "Salted Butter"
    assert qty is None

    # Explicit quantity overrides parsing
    item, qty = parse_item_and_quantity("eggs", explicit_quantity="1 dozen")
    assert item == "Eggs"
    assert qty == "1 dozen"

    with pytest.raises(InvalidInputError):
        parse_item_and_quantity("   ")


def test_speech_formatters_no_markdown_and_bounded_length() -> None:
    spoken_add = format_added_spoken("Whole Milk", "2 liters", "groceries")
    assert "2 liters of Whole Milk" in spoken_add
    assert len(spoken_add) <= 300
    assert "*" not in spoken_add
    assert '"' not in spoken_add

    spoken_check = format_checked_off_spoken("Organic Eggs", "shopping")
    assert "Checked off Organic Eggs" in spoken_check
    assert len(spoken_check) <= 300

    spoken_remove = format_removed_spoken("Bread", "shopping")
    assert "Removed Bread" in spoken_remove
    assert len(spoken_remove) <= 300

    spoken_clear = format_cleared_spoken(3, "shopping")
    assert "Cleared 3 checked items" in spoken_clear
    assert len(spoken_clear) <= 300

    spoken_clear_single = format_cleared_spoken(1, "shopping")
    assert "Cleared 1 checked item" in spoken_clear_single


def test_format_list_items_spoken_scenarios() -> None:
    # Empty
    empty_items: list[dict[str, Any]] = []
    assert "currently empty" in format_list_items_spoken("groceries", empty_items)

    # 1 item
    items_1: list[dict[str, Any]] = [
        {"item_name": "Milk", "quantity": "1 gallon", "checked": False}
    ]
    s1 = format_list_items_spoken("shopping", items_1)
    assert "1 item: 1 gallon Milk" in s1

    # 2 items
    items_2: list[dict[str, Any]] = [
        {"item_name": "Milk", "quantity": None, "checked": False},
        {"item_name": "Eggs", "quantity": "1 dozen", "checked": False},
    ]
    s2 = format_list_items_spoken("shopping", items_2)
    assert "2 items: Milk and 1 dozen Eggs" in s2

    # >5 items capped
    items_many: list[dict[str, Any]] = [
        {"item_name": f"Item {i}", "quantity": None, "checked": False} for i in range(1, 9)
    ]
    sm = format_list_items_spoken("shopping", items_many)
    assert "8 items" in sm
    assert "and 3 more" in sm
    assert len(sm) <= 300
