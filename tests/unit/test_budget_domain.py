"""Unit tests for budget domain calculations and leap year handling (T6.2)."""

from __future__ import annotations

from datetime import UTC, datetime

from sahayak.modules.finance.domain.budgets import (
    analyze_budget,
    calculate_month_period,
    format_budget_list_spoken,
    format_budget_removed_spoken,
    format_budget_set_spoken,
    format_budget_status_spoken,
)


def test_calculate_month_period_february_leap_year() -> None:
    """February in leap year (2024) must have 29 days."""
    ref_dt = datetime(2024, 2, 15, 12, 0, 0, tzinfo=UTC)
    period = calculate_month_period(reference_utc=ref_dt, tz_identifier="UTC")

    assert period.year == 2024
    assert period.month == 2
    assert period.days_in_month == 29
    assert period.day_of_month == 15
    assert period.days_remaining == 14
    assert period.start_utc.day == 1
    assert period.end_utc.day == 29


def test_calculate_month_period_february_non_leap_year() -> None:
    """February in non-leap year (2023) must have 28 days."""
    ref_dt = datetime(2023, 2, 10, 8, 30, 0, tzinfo=UTC)
    period = calculate_month_period(reference_utc=ref_dt, tz_identifier="UTC")

    assert period.year == 2023
    assert period.month == 2
    assert period.days_in_month == 28
    assert period.day_of_month == 10
    assert period.days_remaining == 18
    assert period.start_utc.day == 1
    assert period.end_utc.day == 28


def test_calculate_month_period_timezone_offset() -> None:
    """Month period correctly shifts relative to specified timezone."""
    # Near midnight UTC on 31st Oct, which is Nov 1st in Asia/Kolkata (+5:30)
    ref_dt = datetime(2026, 10, 31, 20, 0, 0, tzinfo=UTC)
    period = calculate_month_period(reference_utc=ref_dt, tz_identifier="Asia/Kolkata")

    assert period.year == 2026
    assert period.month == 11
    assert period.day_of_month == 1
    assert period.days_in_month == 30


def test_analyze_budget_normal_standing() -> None:
    """Budget standing with healthy buffer remaining."""
    ref_dt = datetime(2026, 10, 15, 12, 0, 0, tzinfo=UTC)
    period = calculate_month_period(reference_utc=ref_dt, tz_identifier="UTC")

    analysis = analyze_budget(
        category="groceries",
        currency="INR",
        budget_minor=500000,  # 5,000 INR
        spent_minor=200000,  # 2,000 INR
        period=period,
    )

    assert analysis.budget_minor == 500000
    assert analysis.spent_minor == 200000
    assert analysis.remaining_minor == 300000
    assert analysis.is_overspent is False
    assert analysis.percentage_used == 40.0
    assert analysis.threshold_crossed is None
    assert analysis.projected_overspend_minor == 0


def test_analyze_budget_warning_80_threshold() -> None:
    """Budget warning triggered at >= 80% consumption."""
    ref_dt = datetime(2026, 10, 15, 12, 0, 0, tzinfo=UTC)
    period = calculate_month_period(reference_utc=ref_dt, tz_identifier="UTC")

    analysis = analyze_budget(
        category="dining",
        currency="INR",
        budget_minor=100000,  # 1,000 INR
        spent_minor=85000,  # 850 INR (85%)
        period=period,
    )

    assert analysis.threshold_crossed == "warning_80"
    assert analysis.is_overspent is False
    assert analysis.percentage_used == 85.0
    assert analysis.projected_overspend_minor > 0


def test_analyze_budget_exceeded_threshold() -> None:
    """Budget exceeded when spent > budget."""
    ref_dt = datetime(2026, 10, 20, 12, 0, 0, tzinfo=UTC)
    period = calculate_month_period(reference_utc=ref_dt, tz_identifier="UTC")

    analysis = analyze_budget(
        category="shopping",
        currency="INR",
        budget_minor=100000,  # 1,000 INR
        spent_minor=120000,  # 1,200 INR
        period=period,
    )

    assert analysis.threshold_crossed == "exceeded"
    assert analysis.is_overspent is True
    assert analysis.remaining_minor == -20000


def test_spoken_formatters_length_and_symbols() -> None:
    """Spoken summaries must be <= 300 chars and clean of forbidden characters."""
    ref_dt = datetime(2026, 10, 10, 12, 0, 0, tzinfo=UTC)
    period = calculate_month_period(reference_utc=ref_dt, tz_identifier="UTC")

    set_spoken = format_budget_set_spoken("groceries", 500000, "INR")
    assert len(set_spoken) <= 300
    assert '"' not in set_spoken and "*" not in set_spoken

    analysis = analyze_budget("groceries", "INR", 500000, 420000, period)
    status_spoken = format_budget_status_spoken(analysis)
    assert len(status_spoken) <= 300
    assert '"' not in status_spoken and "`" not in status_spoken

    list_spoken = format_budget_list_spoken([analysis])
    assert len(list_spoken) <= 300

    removed_spoken = format_budget_removed_spoken("groceries")
    assert "groceries" in removed_spoken
