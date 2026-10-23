"""Domain calculations and spoken formatters for category budgets (T6.2).

All calculations strictly use integer minor units and timezones with leap year handling.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sahayak.modules.finance.domain.money import format_money_spoken


@dataclass(frozen=True)
class MonthPeriod:
    """Calculated start and end boundaries of a month in UTC."""

    year: int
    month: int
    days_in_month: int
    day_of_month: int
    days_remaining: int
    start_utc: datetime
    end_utc: datetime


def calculate_month_period(
    reference_utc: datetime | None = None,
    tz_identifier: str | None = None,
) -> MonthPeriod:
    """Calculate the precise month boundaries for a user's local timezone.

    Correctly handles leap years (e.g. Feb 29) and month end dates.
    """
    now_utc = reference_utc or datetime.now(UTC)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=UTC)

    try:
        user_tz = ZoneInfo(tz_identifier) if tz_identifier else UTC
    except (ZoneInfoNotFoundError, ValueError):
        user_tz = UTC

    local_dt = now_utc.astimezone(user_tz)
    year = local_dt.year
    month = local_dt.month
    day = local_dt.day

    _, days_in_month = calendar.monthrange(year, month)
    days_remaining = max(0, days_in_month - day)

    local_start = datetime(year, month, 1, 0, 0, 0, tzinfo=user_tz)
    local_end = datetime(year, month, days_in_month, 23, 59, 59, 999999, tzinfo=user_tz)

    return MonthPeriod(
        year=year,
        month=month,
        days_in_month=days_in_month,
        day_of_month=day,
        days_remaining=days_remaining,
        start_utc=local_start.astimezone(UTC),
        end_utc=local_end.astimezone(UTC),
    )


@dataclass(frozen=True)
class BudgetAnalysis:
    """Calculated financial health and burn rate of a category budget."""

    category: str
    currency: str
    budget_minor: int
    spent_minor: int
    remaining_minor: int
    is_overspent: bool
    percentage_used: float
    projected_overspend_minor: int
    threshold_crossed: str | None  # "exceeded", "warning_80", or None
    days_remaining: int


def analyze_budget(
    category: str,
    currency: str,
    budget_minor: int,
    spent_minor: int,
    period: MonthPeriod,
) -> BudgetAnalysis:
    """Analyze category spending against budget cap and project run rate."""
    remaining_minor = budget_minor - spent_minor
    is_overspent = remaining_minor < 0

    percentage = round((spent_minor / budget_minor) * 100, 1) if budget_minor > 0 else 0.0

    # Project end-of-month run rate
    days_passed = max(1, period.day_of_month)
    projected_total_minor = int((spent_minor / days_passed) * period.days_in_month)
    projected_overspend_minor = max(0, projected_total_minor - budget_minor)

    # Threshold alerts
    threshold: str | None = None
    if spent_minor >= budget_minor:
        threshold = "exceeded"
    elif spent_minor >= int(budget_minor * 0.8):
        threshold = "warning_80"

    return BudgetAnalysis(
        category=category,
        currency=currency,
        budget_minor=budget_minor,
        spent_minor=spent_minor,
        remaining_minor=remaining_minor,
        is_overspent=is_overspent,
        percentage_used=percentage,
        projected_overspend_minor=projected_overspend_minor,
        threshold_crossed=threshold,
        days_remaining=period.days_remaining,
    )


def format_budget_set_spoken(category: str, amount_minor: int, currency: str) -> str:
    """Generate spoken confirmation after setting a category budget."""
    spoken_amount = format_money_spoken(amount_minor, currency)
    return f"Your monthly {category} budget has been set to {spoken_amount}."


def format_budget_status_spoken(analysis: BudgetAnalysis) -> str:
    """Generate spoken report on budget standing under 300 chars."""
    spent = format_money_spoken(analysis.spent_minor, analysis.currency)
    budget = format_money_spoken(analysis.budget_minor, analysis.currency)

    if analysis.is_overspent:
        over = format_money_spoken(abs(analysis.remaining_minor), analysis.currency)
        return (
            f"You have spent {spent} of your {budget} {analysis.category} budget. "
            f"You are {over} over budget with {analysis.days_remaining} days left in the month."
        )

    remaining = format_money_spoken(analysis.remaining_minor, analysis.currency)
    if analysis.threshold_crossed == "warning_80":
        return (
            f"You have spent {spent} of your {budget} {analysis.category} budget, "
            f"which is {int(analysis.percentage_used)} percent. "
            f"{remaining} remaining with {analysis.days_remaining} days left."
        )

    return (
        f"You have spent {spent} of your {budget} {analysis.category} budget. "
        f"{remaining} remaining with {analysis.days_remaining} days left in the month."
    )


def format_budget_list_spoken(analyses: list[BudgetAnalysis]) -> str:
    """Generate spoken summary across multiple active category budgets."""
    if not analyses:
        return "You have no active budgets set. Say, set grocery budget to 5000 rupees to begin."

    parts: list[str] = []
    for a in analyses[:4]:  # Voice rule: max 4-5 items
        rem = format_money_spoken(max(0, a.remaining_minor), a.currency)
        if a.is_overspent:
            parts.append(f"{a.category} is over budget")
        else:
            parts.append(f"{a.category} with {rem} remaining")

    n = len(analyses)
    count_str = f"{n} category budget" if n == 1 else f"{n} category budgets"
    return f"You have {count_str}: {', and '.join(parts)}."


def format_budget_removed_spoken(category: str) -> str:
    """Generate spoken confirmation when a budget is removed."""
    return f"Your {category} budget has been removed."
