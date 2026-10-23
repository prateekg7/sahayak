"""Domain logic for business orders, status transitions, and voice formatters (T10.1)."""

from __future__ import annotations

import re
from typing import Any

from sahayak.core.errors import InvalidInputError

VALID_STATUSES = {"pending", "packed", "shipped", "delivered", "cancelled"}

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"packed", "cancelled"},
    "packed": {"shipped", "cancelled"},
    "shipped": {"delivered", "cancelled"},
    "delivered": set(),
    "cancelled": set(),
}


def sanitize_spoken_text(text: str) -> str:
    """Strip markdown formatting, emojis, quotes, and excessive whitespace."""
    no_md = re.sub(r"[*_`#~\[\]()]", "", text)
    no_quotes = no_md.replace('"', "").replace("'", "")
    clean = re.sub(r"\s+", " ", no_quotes).strip()
    return clean[:300]


def format_currency_spoken(amount_minor: int, currency: str = "INR") -> str:
    """Format integer minor units into natural voice representation."""
    curr = currency.upper()
    unit_name = "rupees" if curr == "INR" else ("dollars" if curr == "USD" else curr.lower())

    if amount_minor % 100 == 0:
        main_units = amount_minor // 100
        return f"{main_units} {unit_name}"

    units = amount_minor / 100.0
    return f"{units:.2f} {unit_name}"


def validate_status_transition(current_status: str, new_status: str, order_number: int) -> None:
    """Validate that the status transition conforms to the order state machine."""
    c_status = current_status.strip().lower()
    n_status = new_status.strip().lower()

    if n_status not in VALID_STATUSES:
        allowed = ", ".join(sorted(VALID_STATUSES))
        raise InvalidInputError(
            spoken=f"Status {n_status} is invalid. Valid statuses are {allowed}.",
            detail=f"Invalid status '{new_status}'",
        )

    if c_status == n_status:
        return

    allowed_targets = ALLOWED_TRANSITIONS.get(c_status, set())
    if n_status not in allowed_targets:
        if c_status in {"delivered", "cancelled"}:
            spoken_err = f"Order {order_number} is already {c_status} and cannot be modified."
        else:
            targets_str = " or ".join(sorted(allowed_targets)) if allowed_targets else "none"
            spoken_err = (
                f"Cannot change order {order_number} from {c_status} directly to {n_status}. "
                f"Next valid status is {targets_str}."
            )
        raise InvalidInputError(
            spoken=sanitize_spoken_text(spoken_err),
            detail=(
                f"Illegal order transition '{c_status}' -> '{n_status}' for order {order_number}"
            ),
        )


def format_order_created_spoken(
    order_number: int,
    total_minor: int,
    currency: str,
    customer_name: str | None = None,
) -> str:
    """Voice summary when an order is created."""
    amount_str = format_currency_spoken(total_minor, currency)
    customer_part = f" for {customer_name}" if customer_name else ""
    return sanitize_spoken_text(
        f"Created order {order_number}{customer_part} totaling {amount_str}."
    )


def format_order_status_updated_spoken(order_number: int, new_status: str) -> str:
    """Voice summary when an order status is updated."""
    return sanitize_spoken_text(f"Marked order {order_number} as {new_status}.")


def format_pending_orders_spoken(orders: list[dict[str, Any]]) -> str:
    """Voice summary of pending and in-progress orders."""
    if not orders:
        return sanitize_spoken_text("You have no pending orders.")

    count = len(orders)
    summaries: list[str] = []
    for o in orders[:4]:
        num = o.get("order_number", "")
        status = o.get("status", "pending")
        cust = o.get("customer_name")
        c_part = f" for {cust}" if cust else ""
        summaries.append(f"order {num}{c_part} is {status}")

    combined = ", ".join(summaries)
    more = f" and {count - 4} more" if count > 4 else ""
    suffix = "s" if count != 1 else ""
    return sanitize_spoken_text(f"You have {count} active order{suffix}: {combined}{more}.")


def format_order_details_spoken(
    order: dict[str, Any],
    items: list[dict[str, Any]],
) -> str:
    """Voice summary of order details and line items."""
    num = order.get("order_number", "")
    status = order.get("status", "pending")
    total_minor = order.get("total_amount_minor", 0)
    currency = order.get("currency", "INR")
    cust = order.get("customer_name")
    amount_str = format_currency_spoken(total_minor, currency)

    cust_part = f" for {cust}" if cust else ""
    if not items:
        return sanitize_spoken_text(f"Order {num}{cust_part} is {status} totaling {amount_str}.")

    item_names = [f"{it.get('quantity', 1)} {it.get('item_name')}" for it in items[:3]]
    items_str = ", ".join(item_names)
    more = f" plus {len(items) - 3} more items" if len(items) > 3 else ""

    return sanitize_spoken_text(
        f"Order {num}{cust_part} is {status} totaling {amount_str} with {items_str}{more}."
    )
