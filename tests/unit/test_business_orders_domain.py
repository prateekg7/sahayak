"""Unit tests for business orders domain logic, transitions, and voice formatting (T10.1)."""

from __future__ import annotations

import pytest

from sahayak.core.errors import InvalidInputError
from sahayak.modules.business.domain.orders import (
    format_currency_spoken,
    format_order_created_spoken,
    format_order_details_spoken,
    format_order_status_updated_spoken,
    format_pending_orders_spoken,
    validate_status_transition,
)


def test_format_currency_spoken() -> None:
    assert format_currency_spoken(50000, "INR") == "500 rupees"
    assert format_currency_spoken(1250, "INR") == "12.50 rupees"
    assert format_currency_spoken(1000, "USD") == "10 dollars"


def test_valid_status_transitions() -> None:
    # pending -> packed or cancelled
    validate_status_transition("pending", "packed", 1)
    validate_status_transition("pending", "cancelled", 1)
    validate_status_transition("pending", "pending", 1)

    # packed -> shipped or cancelled
    validate_status_transition("packed", "shipped", 1)
    validate_status_transition("packed", "cancelled", 1)

    # shipped -> delivered or cancelled
    validate_status_transition("shipped", "delivered", 1)
    validate_status_transition("shipped", "cancelled", 1)


def test_illegal_status_transitions() -> None:
    with pytest.raises(InvalidInputError, match="directly to delivered"):
        validate_status_transition("pending", "delivered", 1)

    with pytest.raises(InvalidInputError, match="directly to pending"):
        validate_status_transition("packed", "pending", 2)

    with pytest.raises(InvalidInputError, match="already delivered and cannot"):
        validate_status_transition("delivered", "shipped", 3)

    with pytest.raises(InvalidInputError, match="already cancelled and cannot"):
        validate_status_transition("cancelled", "pending", 4)

    with pytest.raises(InvalidInputError, match="Status unknown_status is invalid"):
        validate_status_transition("pending", "unknown_status", 5)


def test_voice_formatting_rules() -> None:
    created = format_order_created_spoken(12, 45000, "INR", "Ramesh")
    assert len(created) <= 300
    assert "Created order 12 for Ramesh totaling 450 rupees." in created
    assert "*" not in created and "#" not in created and "`" not in created

    updated = format_order_status_updated_spoken(12, "shipped")
    assert len(updated) <= 300
    assert "Marked order 12 as shipped." in updated

    pending = format_pending_orders_spoken(
        [
            {"order_number": 1, "status": "pending", "customer_name": "Alice"},
            {"order_number": 2, "status": "packed", "customer_name": "Bob"},
        ]
    )
    assert len(pending) <= 300
    assert "order 1 for Alice is pending" in pending
    assert "order 2 for Bob is packed" in pending

    order_payload = {
        "order_number": 1,
        "status": "pending",
        "total_amount_minor": 15000,
        "currency": "INR",
        "customer_name": "Alice",
    }
    details = format_order_details_spoken(
        order_payload,
        [
            {"item_name": "Hardbound Notebook", "quantity": 2},
            {"item_name": "Gel Pen", "quantity": 5},
        ],
    )
    assert len(details) <= 300
    assert "Order 1 for Alice is pending totaling 150 rupees" in details
