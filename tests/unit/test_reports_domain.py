"""Unit tests for finance reports domain logic and bill roll-forwards (T6.4)."""

from __future__ import annotations

from datetime import UTC, date, datetime

from sahayak.modules.finance.domain.reports import (
    calculate_initial_due_date,
    calculate_report_period,
    compare_spending,
    compute_next_due_date,
    format_add_bill_spoken,
    format_by_category_spoken,
    format_mark_paid_spoken,
    format_summary_spoken,
)


def test_calculate_report_period_monthly() -> None:
    # Test middle of March 2026
    now = datetime(2026, 3, 15, 12, 0, 0, tzinfo=UTC)
    curr_start, curr_end, prev_start, prev_end = calculate_report_period("monthly", now)

    assert curr_start == datetime(2026, 3, 1, 0, 0, 0, tzinfo=UTC)
    assert curr_end == datetime(2026, 3, 31, 23, 59, 59, 999999, tzinfo=UTC)
    assert prev_start == datetime(2026, 2, 1, 0, 0, 0, tzinfo=UTC)
    assert prev_end == datetime(2026, 2, 28, 23, 59, 59, 999999, tzinfo=UTC)


def test_calculate_report_period_january_rollover() -> None:
    # Test January 2026 - previous month must be December 2025
    now = datetime(2026, 1, 10, 10, 0, 0, tzinfo=UTC)
    curr_start, curr_end, prev_start, prev_end = calculate_report_period("monthly", now)

    assert curr_start == datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
    assert curr_end == datetime(2026, 1, 31, 23, 59, 59, 999999, tzinfo=UTC)
    assert prev_start == datetime(2025, 12, 1, 0, 0, 0, tzinfo=UTC)
    assert prev_end == datetime(2025, 12, 31, 23, 59, 59, 999999, tzinfo=UTC)


def test_calculate_report_period_weekly() -> None:
    now = datetime(2026, 3, 22, 12, 0, 0, tzinfo=UTC)
    curr_start, curr_end, prev_start, prev_end = calculate_report_period("weekly", now)

    assert curr_end == now
    assert curr_start == datetime(2026, 3, 15, 12, 0, 0, tzinfo=UTC)
    assert prev_end == curr_start
    assert prev_start == datetime(2026, 3, 8, 12, 0, 0, tzinfo=UTC)


def test_compute_next_due_date_monthly() -> None:
    # Roll from Jan 15 to Feb 15
    next_date = compute_next_due_date(due_day=15, frequency="monthly", from_date=date(2026, 1, 15))
    assert next_date == date(2026, 2, 15)

    # Roll from Jan 31 to Feb (clamped to 28 in non-leap year 2026)
    next_clamped = compute_next_due_date(
        due_day=31, frequency="monthly", from_date=date(2026, 1, 31)
    )
    assert next_clamped == date(2026, 2, 28)

    # Roll across year boundary: Dec 10 to Jan 10
    year_roll = compute_next_due_date(due_day=10, frequency="monthly", from_date=date(2026, 12, 10))
    assert year_roll == date(2027, 1, 10)


def test_compute_next_due_date_weekly_and_yearly() -> None:
    # Weekly: +7 days
    w_date = compute_next_due_date(due_day=1, frequency="weekly", from_date=date(2026, 5, 10))
    assert w_date == date(2026, 5, 17)

    # Yearly: +1 year
    y_date = compute_next_due_date(due_day=15, frequency="yearly", from_date=date(2026, 5, 15))
    assert y_date == date(2027, 5, 15)


def test_calculate_initial_due_date() -> None:
    # Today is May 10, bill due on 20th -> May 20
    d1 = calculate_initial_due_date(due_day=20, frequency="monthly", today=date(2026, 5, 10))
    assert d1 == date(2026, 5, 20)

    # Today is May 25, bill due on 10th -> June 10
    d2 = calculate_initial_due_date(due_day=10, frequency="monthly", today=date(2026, 5, 25))
    assert d2 == date(2026, 6, 10)


def test_compare_spending() -> None:
    diff, pct = compare_spending(15000, 10000)
    assert diff == 5000
    assert pct == 50.0

    diff2, pct2 = compare_spending(8000, 10000)
    assert diff2 == -2000
    assert pct2 == -20.0

    diff3, pct3 = compare_spending(5000, 0)
    assert diff3 == 5000
    assert pct3 is None


def test_spoken_summary_constraints() -> None:
    spoken = format_summary_spoken(
        period="monthly",
        current_minor=1200000,
        previous_minor=1000000,
        diff_minor=200000,
        pct=20.0,
        currency="INR",
        categories_count=4,
        top_category="groceries",
        top_cat_minor=500000,
        upcoming_bills_count=2,
        upcoming_bills_minor=300000,
    )
    assert len(spoken) <= 300
    assert '"' not in spoken
    assert "₹" not in spoken
    assert "rupees" in spoken
    assert "groceries" in spoken.lower()


def test_spoken_formatters_no_symbols() -> None:
    cat_spoken = format_by_category_spoken(
        period="monthly",
        breakdown=[("groceries", 500000, 50.0), ("dining", 300000, 30.0)],
        currency="INR",
    )
    assert len(cat_spoken) <= 300
    assert "₹" not in cat_spoken

    add_spoken = format_add_bill_spoken("Rent", 2000000, "INR", 5, date(2026, 6, 5))
    assert len(add_spoken) <= 300
    assert "Rent" in add_spoken
    assert "rupees" in add_spoken

    mark_spoken = format_mark_paid_spoken("Rent", 2000000, "INR", date(2026, 7, 5))
    assert len(mark_spoken) <= 300
    assert "paid" in mark_spoken
