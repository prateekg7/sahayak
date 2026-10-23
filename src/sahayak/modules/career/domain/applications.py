"""Career job application tracking domain logic and speech formatting (T8.2)."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from sahayak.modules.career.domain.rubric import sanitize_spoken_text

VALID_STATUSES = {
    "applied",
    "screening",
    "interviewing",
    "offer",
    "rejected",
    "withdrawn",
}


def normalize_status(raw_status: str) -> str:
    """Normalize user input or spoken forms into canonical application status."""
    cleaned = raw_status.strip().lower()
    if cleaned in VALID_STATUSES:
        return cleaned

    mapping = {
        "apply": "applied",
        "submitting": "applied",
        "submitted": "applied",
        "screen": "screening",
        "recruiter": "screening",
        "hr": "screening",
        "phone screen": "screening",
        "interview": "interviewing",
        "tech round": "interviewing",
        "rounds": "interviewing",
        "offered": "offer",
        "job offer": "offer",
        "reject": "rejected",
        "no": "rejected",
        "withdraw": "withdrawn",
        "cancelled": "withdrawn",
    }
    return mapping.get(cleaned, cleaned)


def parse_follow_up_date(
    raw_date: str | None,
    base_time: datetime | None = None,
) -> datetime | None:
    """Parse natural or ISO date string for follow up deadlines."""
    if not raw_date or not raw_date.strip():
        return None

    now = base_time or datetime.now(UTC)
    s = raw_date.strip().lower()

    if s in ("tomorrow", "in 1 day", "in a day"):
        return now + timedelta(days=1)
    if s in ("in 2 days",):
        return now + timedelta(days=2)
    if s in ("in 3 days",):
        return now + timedelta(days=3)
    if s in ("next week", "in a week", "in 1 week", "in 7 days"):
        return now + timedelta(days=7)
    if s in ("in 2 weeks", "in 14 days"):
        return now + timedelta(days=14)

    # Match "in N days"
    match_days = re.match(r"in\s+(\d+)\s+days?", s)
    if match_days:
        days = int(match_days.group(1))
        return now + timedelta(days=days)

    # Match ISO format YYYY-MM-DD
    try:
        parsed_dt = datetime.fromisoformat(s)
        if parsed_dt.tzinfo is None:
            parsed_dt = parsed_dt.replace(tzinfo=UTC)
        return parsed_dt
    except (ValueError, TypeError):
        pass

    return None


def format_pipeline_summary(
    applications: list[dict[str, object]],
    due_count: int = 0,
) -> str:
    """Format voice-first concise summary of active job pipeline (<= 300 chars)."""
    if not applications:
        return "You have no tracked job applications yet. Say add application to track one."

    total = len(applications)
    status_counts: dict[str, int] = {}
    for a in applications:
        st = str(a.get("status", "applied"))
        status_counts[st] = status_counts.get(st, 0) + 1

    parts = []
    for st in ("interviewing", "screening", "offer", "applied"):
        if st in status_counts:
            parts.append(f"{status_counts[st]} {st}")

    breakdown = ", ".join(parts) if parts else f"{total} total"
    follow_up_phrase = ""
    if due_count > 0:
        follow_up_phrase = (
            f" You have {due_count} follow-up deadline{'s' if due_count > 1 else ''} due."
        )

    text = f"You have {total} job applications tracked: {breakdown}.{follow_up_phrase}"
    return sanitize_spoken_text(text)
