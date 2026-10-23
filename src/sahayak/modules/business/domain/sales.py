"""Domain logic for business sales reporting and stock alerts (T10.3)."""

from __future__ import annotations

from typing import Any

from sahayak.modules.business.domain.orders import format_currency_spoken


def format_sales_today_spoken(
    revenue_minor: int,
    order_count: int,
    currency: str = "INR",
) -> str:
    """Format voice summary for today's sales."""
    if order_count == 0:
        return "No orders have been placed today."

    rev_str = format_currency_spoken(revenue_minor, currency)
    order_phrase = "1 order" if order_count == 1 else f"{order_count} orders"
    text = f"Today you had {order_phrase} totaling {rev_str}."
    return text[:300]


def format_sales_week_spoken(
    revenue_minor: int,
    order_count: int,
    currency: str = "INR",
) -> str:
    """Format voice summary for this week's (last 7 days) sales."""
    if order_count == 0:
        return "No orders have been placed in the last 7 days."

    rev_str = format_currency_spoken(revenue_minor, currency)
    order_phrase = "1 order" if order_count == 1 else f"{order_count} orders"
    text = f"In the last 7 days you had {order_phrase} totaling {rev_str}."
    return text[:300]


def format_top_products_spoken(
    products: list[dict[str, Any]],
    currency: str = "INR",
) -> str:
    """Format voice summary for top selling products."""
    if not products:
        return "No product sales have been recorded yet."

    phrases: list[str] = []
    for item in products[:5]:
        name = item.get("name", "Item")
        qty = item.get("units_sold", 0)
        phrases.append(f"{name} with {qty} units sold")

    text = "Top selling products: " + ", ".join(phrases) + "."
    return text[:300]


def format_low_stock_spoken(products: list[dict[str, Any]]) -> str:
    """Format voice summary for products at or below low stock threshold."""
    if not products:
        return "All products are well stocked. No low stock alerts."

    phrases: list[str] = []
    for item in products[:5]:
        name = item.get("name", "Item")
        stock = item.get("stock_level", 0)
        phrases.append(f"{name} has {stock} units left")

    summary = "Low stock alert: " + ", ".join(phrases) + "."
    if len(products) > 5:
        remaining = len(products) - 5
        summary += f" Plus {remaining} more items low in stock."
    return summary[:300]


def format_product_added_spoken(
    name: str,
    stock_level: int,
    threshold: int,
) -> str:
    """Format voice summary for registering or updating a product."""
    unit_phrase = "1 unit" if stock_level == 1 else f"{stock_level} units"
    text = f"Product {name} updated with {unit_phrase} in stock and low stock alert at {threshold}."
    return text[:300]
