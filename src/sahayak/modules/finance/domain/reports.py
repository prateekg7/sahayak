"""Domain models, roll-forward logic, and spoken formatters for financial reports (T6.4)."""

from __future__ import annotations

import calendar
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sahayak.modules.finance.domain.money import format_money_spoken


def calculate_report_period(
    period_type: str, now: datetime
) -> tuple[datetime, datetime, datetime, datetime]:
    """Calculate current and previous time window boundaries for reporting.

    Returns (current_start, current_end, previous_start, previous_end) in UTC.
    """
    period_clean = period_type.lower().strip()
    if period_clean == "weekly":
        current_end = now
        current_start = now - timedelta(days=7)
        previous_end = current_start
        previous_start = current_start - timedelta(days=7)
        return current_start, current_end, previous_start, previous_end

    # Default: monthly
    year = now.year
    month = now.month

    # Current month
    days_in_curr = calendar.monthrange(year, month)[1]
    current_start = datetime(year, month, 1, 0, 0, 0, tzinfo=UTC)
    current_end = datetime(year, month, days_in_curr, 23, 59, 59, 999999, tzinfo=UTC)

    # Previous month
    if month == 1:
        prev_year = year - 1
        prev_month = 12
    else:
        prev_year = year
        prev_month = month - 1

    days_in_prev = calendar.monthrange(prev_year, prev_month)[1]
    previous_start = datetime(prev_year, prev_month, 1, 0, 0, 0, tzinfo=UTC)
    previous_end = datetime(prev_year, prev_month, days_in_prev, 23, 59, 59, 999999, tzinfo=UTC)

    return current_start, current_end, previous_start, previous_end


def compute_next_due_date(due_day: int, frequency: str, from_date: date) -> date:
    """Calculate the next due date after a bill is paid or rolled forward.

    Handles month boundaries, leap years, and clamped day limits cleanly.
    """
    freq_clean = frequency.lower().strip()

    if freq_clean == "weekly":
        return from_date + timedelta(days=7)

    if freq_clean == "yearly":
        target_year = from_date.year + 1
        target_month = from_date.month
        max_days = calendar.monthrange(target_year, target_month)[1]
        target_day = min(due_day, max_days)
        return date(target_year, target_month, target_day)

    # Monthly default
    if from_date.month == 12:
        target_year = from_date.year + 1
        target_month = 1
    else:
        target_year = from_date.year
        target_month = from_date.month + 1

    max_days = calendar.monthrange(target_year, target_month)[1]
    target_day = min(due_day, max_days)
    return date(target_year, target_month, target_day)


def calculate_initial_due_date(due_day: int, frequency: str, today: date) -> date:
    """Determine initial due date when creating a recurring bill."""
    max_days_current = calendar.monthrange(today.year, today.month)[1]
    clamped_day = min(due_day, max_days_current)

    if clamped_day >= today.day:
        return date(today.year, today.month, clamped_day)

    return compute_next_due_date(due_day, frequency, today)


def compare_spending(current_minor: int, previous_minor: int) -> tuple[int, float | None]:
    """Calculate absolute difference and percentage change between two periods."""
    diff = current_minor - previous_minor
    pct = round((diff / previous_minor) * 100, 1) if previous_minor > 0 else None
    return diff, pct


def format_summary_spoken(
    period: str,
    current_minor: int,
    previous_minor: int,
    diff_minor: int,
    pct: float | None,
    currency: str,
    categories_count: int,
    top_category: str | None,
    top_cat_minor: int,
    upcoming_bills_count: int,
    upcoming_bills_minor: int,
) -> str:
    """Generate spoken financial report summary under 300 characters."""
    curr_str = format_money_spoken(current_minor, currency)
    period_label = "This week" if period.lower() == "weekly" else "This month"
    prev_label = "last week" if period.lower() == "weekly" else "last month"

    if current_minor == 0:
        msg = f"{period_label} you have logged zero expenses."
    else:
        msg = f"{period_label} you spent {curr_str} across {categories_count} categories."

        if previous_minor > 0 and pct is not None:
            if diff_minor > 0:
                msg += f" That is up {abs(pct):.0f} percent from {prev_label}."
            elif diff_minor < 0:
                msg += f" That is down {abs(pct):.0f} percent from {prev_label}."
            else:
                msg += f" That matches your spending {prev_label}."

        if top_category and top_cat_minor > 0:
            top_str = format_money_spoken(top_cat_minor, currency)
            msg += f" Top category was {top_category.title()} at {top_str}."

    if upcoming_bills_count > 0:
        bills_str = format_money_spoken(upcoming_bills_minor, currency)
        bill_word = "bill" if upcoming_bills_count == 1 else "bills"
        msg += f" You have {upcoming_bills_count} {bill_word} due soon totaling {bills_str}."

    if len(msg) > 300:
        # Truncate cleanly if edge case occurs
        msg = f"{period_label} spending is {curr_str} across {categories_count} categories."
        if upcoming_bills_count > 0:
            bills_str = format_money_spoken(upcoming_bills_minor, currency)
            msg += f" Upcoming bills total {bills_str}."

    return msg.strip()


def format_by_category_spoken(
    period: str,
    breakdown: list[tuple[str, int, float]],
    currency: str,
) -> str:
    """Generate spoken breakdown of spending by category under 300 chars."""
    period_label = "this week" if period.lower() == "weekly" else "this month"
    if not breakdown:
        return f"You have no spending logged {period_label}."

    items: list[str] = []
    for cat, minor, _pct in breakdown[:4]:
        items.append(f"{cat.title()} {format_money_spoken(minor, currency)}")

    joined = ", ".join(items)
    msg = f"Spending by category {period_label}: {joined}."
    if len(msg) > 300:
        msg = msg[:297] + "..."
    return msg


def format_bills_due_spoken(
    bills: list[Any],
    currency: str,
    days_ahead: int,
) -> str:
    """Generate spoken summary of upcoming bills under 300 chars."""
    if not bills:
        return f"You have no upcoming bills due in the next {days_ahead} days."

    total_minor = sum(b.amount_minor for b in bills)
    total_str = format_money_spoken(total_minor, currency)
    bill_word = "bill" if len(bills) == 1 else "bills"

    items: list[str] = []
    for b in bills[:3]:
        due_str = b.next_due_date.strftime("%B %d")
        items.append(f"{b.name} {format_money_spoken(b.amount_minor, currency)} on {due_str}")

    if len(items) <= 2:
        joined = ", and ".join(items)
    else:
        joined = ", ".join(items[:-1]) + f", and {items[-1]}"

    msg = (
        f"You have {len(bills)} {bill_word} due in the next {days_ahead} "
        f"days totaling {total_str}: {joined}."
    )
    if len(msg) > 300:
        msg = (
            f"You have {len(bills)} {bill_word} due in the next {days_ahead} "
            f"days totaling {total_str}."
        )
    return msg


def format_add_bill_spoken(
    name: str,
    amount_minor: int,
    currency: str,
    due_day: int,
    next_due: date,
) -> str:
    """Generate spoken confirmation for adding a recurring bill."""
    amt_str = format_money_spoken(amount_minor, currency)
    due_str = next_due.strftime("%B %d")
    return (
        f"Added {name} bill of {amt_str} due on day {due_day} of each month. "
        f"Next due date is {due_str}."
    )


def format_mark_paid_spoken(
    name: str,
    amount_minor: int,
    currency: str,
    next_due: date,
) -> str:
    """Generate spoken confirmation for marking a bill paid."""
    amt_str = format_money_spoken(amount_minor, currency)
    due_str = next_due.strftime("%B %d")
    return f"Marked {name} bill of {amt_str} as paid. Next cycle is due on {due_str}."
