"""Unit tests for business sales domain logic and voice formatting (T10.3)."""

from __future__ import annotations

from sahayak.modules.business.domain.sales import (
    format_low_stock_spoken,
    format_product_added_spoken,
    format_sales_today_spoken,
    format_sales_week_spoken,
    format_top_products_spoken,
)


def test_sales_spoken_formatters_comply_with_voice_rules() -> None:
    """Voice formatting rules: <= 300 chars, no markdown (*, #, `), natural phrasing."""
    # Today's sales
    today_none = format_sales_today_spoken(0, 0, "INR")
    assert "No orders have been placed today." in today_none

    today_single = format_sales_today_spoken(15000, 1, "INR")
    assert "Today you had 1 order totaling 150 rupees." in today_single

    today_multi = format_sales_today_spoken(450000, 12, "INR")
    assert len(today_multi) <= 300
    assert "Today you had 12 orders totaling 4500 rupees." in today_multi
    assert "*" not in today_multi

    # Week's sales
    week_none = format_sales_week_spoken(0, 0, "INR")
    assert "No orders have been placed in the last 7 days." in week_none

    week_multi = format_sales_week_spoken(1250000, 48, "INR")
    assert len(week_multi) <= 300
    assert "In the last 7 days you had 48 orders totaling 12500 rupees." in week_multi

    # Top selling products
    top_empty = format_top_products_spoken([], "INR")
    assert "No product sales have been recorded yet." in top_empty

    top_populated = format_top_products_spoken(
        [
            {"name": "Notebook", "units_sold": 25, "revenue_minor": 125000},
            {"name": "Gel Pen", "units_sold": 18, "revenue_minor": 18000},
            {"name": "Eraser", "units_sold": 10, "revenue_minor": 5000},
        ],
        "INR",
    )
    assert len(top_populated) <= 300
    assert "Notebook with 25 units sold" in top_populated
    assert "Gel Pen with 18 units sold" in top_populated

    # Low stock alerts
    low_empty = format_low_stock_spoken([])
    assert "All products are well stocked. No low stock alerts." in low_empty

    low_populated = format_low_stock_spoken(
        [
            {"name": "Milk", "stock_level": 2, "low_stock_threshold": 5},
            {"name": "Bread", "stock_level": 1, "low_stock_threshold": 5},
        ]
    )
    assert len(low_populated) <= 300
    assert "Low stock alert: Milk has 2 units left, Bread has 1 units left." in low_populated

    low_overflow = format_low_stock_spoken(
        [{"name": f"Item {i}", "stock_level": 1, "low_stock_threshold": 5} for i in range(8)]
    )
    assert "Plus 3 more items low in stock." in low_overflow

    # Product added / updated
    prod_add_single = format_product_added_spoken("Special Tea", 1, 5)
    assert "1 unit in stock and low stock alert at 5" in prod_add_single

    prod_add_multi = format_product_added_spoken("Sugar", 50, 10)
    assert "50 units in stock and low stock alert at 10" in prod_add_multi
