"""Unit tests for money domain arithmetic, parsing safeguards, and category normalization (T6.1)."""

from __future__ import annotations

import pytest

from sahayak.core.errors import InvalidInputError
from sahayak.modules.finance.domain.categories import normalize_category
from sahayak.modules.finance.domain.money import (
    Money,
    format_money_display,
    format_money_spoken,
    parse_to_minor_units,
)


def test_money_value_object_type_safety() -> None:
    m = Money(amount_minor=20000, currency="INR")
    assert m.amount_minor == 20000
    assert m.currency == "INR"

    # Floats are strictly prohibited
    with pytest.raises(TypeError, match="amount_minor must be an integer, never float"):
        Money(amount_minor=200.50, currency="INR")  # type: ignore[arg-type]


def test_parse_to_minor_units_valid() -> None:
    assert parse_to_minor_units(200) == 20000
    assert parse_to_minor_units("200") == 20000
    assert parse_to_minor_units("200.50") == 20050
    assert parse_to_minor_units("₹200.50") == 20050
    assert parse_to_minor_units("$15.99") == 1599
    assert parse_to_minor_units("1,500") == 150000
    assert parse_to_minor_units("0.50") == 50


def test_parse_to_minor_units_invalid() -> None:
    with pytest.raises(InvalidInputError, match="Amount is required"):
        parse_to_minor_units(None)

    with pytest.raises(InvalidInputError, match="cannot be empty"):
        parse_to_minor_units("   ")

    with pytest.raises(InvalidInputError, match="must be greater than zero"):
        parse_to_minor_units(0)

    with pytest.raises(InvalidInputError, match="must be greater than zero"):
        parse_to_minor_units("-50")

    with pytest.raises(InvalidInputError, match="Invalid monetary amount"):
        parse_to_minor_units("abc")


def test_format_money_spoken() -> None:
    assert format_money_spoken(20000, "INR") == "200 rupees"
    assert format_money_spoken(100, "INR") == "1 rupee"
    assert format_money_spoken(50, "INR") == "50 paise"
    assert format_money_spoken(20050, "INR") == "200 rupees and 50 paise"

    assert format_money_spoken(1500, "USD") == "15 dollars"
    assert format_money_spoken(100, "USD") == "1 dollar"
    assert format_money_spoken(99, "USD") == "99 cents"
    assert format_money_spoken(1599, "USD") == "15 dollars and 99 cents"


def test_format_money_display() -> None:
    assert format_money_display(20050, "INR") == "₹200.50"
    assert format_money_display(1599, "USD") == "$15.99"
    assert format_money_display(1000, "EUR") == "€10.00"


def test_normalize_category() -> None:
    assert normalize_category("groceries") == "groceries"
    assert normalize_category("milk", "from local dairy") == "groceries"
    assert normalize_category("uber", "ride to airport") == "transport"
    assert normalize_category(None, "dinner at Italian cafe") == "food"
    assert normalize_category(None, "electricity bill payment") == "utilities"
    assert normalize_category(None, "netflix monthly subscription") == "entertainment"
    assert normalize_category("custom_cat") == "custom_cat"
    assert normalize_category(None, None) == "other"
