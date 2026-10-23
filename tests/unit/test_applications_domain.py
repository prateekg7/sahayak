"""Unit tests for job application domain logic and speech formatting (T8.2)."""

from __future__ import annotations

from datetime import UTC, datetime

from sahayak.modules.career.domain.applications import (
    format_pipeline_summary,
    normalize_status,
    parse_follow_up_date,
)


def test_normalize_status() -> None:
    assert normalize_status("applied") == "applied"
    assert normalize_status("interview") == "interviewing"
    assert normalize_status("phone screen") == "screening"
    assert normalize_status("recruiter") == "screening"
    assert normalize_status("offered") == "offer"
    assert normalize_status("reject") == "rejected"
    assert normalize_status("cancelled") == "withdrawn"


def test_parse_follow_up_date() -> None:
    base = datetime(2026, 10, 24, 12, 0, 0, tzinfo=UTC)

    # Relative tokens
    dt_tom = parse_follow_up_date("tomorrow", base_time=base)
    assert dt_tom is not None
    assert (dt_tom - base).days == 1

    dt_3d = parse_follow_up_date("in 3 days", base_time=base)
    assert dt_3d is not None
    assert (dt_3d - base).days == 3

    dt_week = parse_follow_up_date("next week", base_time=base)
    assert dt_week is not None
    assert (dt_week - base).days == 7

    # ISO date string
    dt_iso = parse_follow_up_date("2026-11-15", base_time=base)
    assert dt_iso is not None
    assert dt_iso.year == 2026 and dt_iso.month == 11 and dt_iso.day == 15

    # Invalid string returns None
    assert parse_follow_up_date("invalid date", base_time=base) is None
    assert parse_follow_up_date(None) is None


def test_format_pipeline_summary_speech() -> None:
    empty_summary = format_pipeline_summary([])
    assert "no tracked job applications" in empty_summary.lower()

    sample_apps: list[dict[str, object]] = [
        {"company": "Google", "status": "interviewing"},
        {"company": "Stripe", "status": "interviewing"},
        {"company": "Meta", "status": "screening"},
        {"company": "Amazon", "status": "applied"},
    ]
    summary = format_pipeline_summary(sample_apps, due_count=2)
    assert "4 job applications tracked" in summary
    assert "2 interviewing" in summary
    assert "1 screening" in summary
    assert "2 follow-up deadlines due" in summary
    assert len(summary) <= 300
    assert "*" not in summary and "`" not in summary
