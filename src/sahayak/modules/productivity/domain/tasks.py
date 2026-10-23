"""Pure domain models, date parsing, and speech formatting for tasks (T5.1)."""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from enum import Enum
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sahayak.core.errors import InvalidInputError


class TaskPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TaskStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


DAYS_OF_WEEK = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

MONTH_NAMES = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


def resolve_user_zone(timezone_str: str) -> ZoneInfo:
    """Resolve ZoneInfo from timezone string with fallback to UTC."""
    try:
        return ZoneInfo(timezone_str)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def parse_due_date(
    due_str: str | None,
    reference_dt: datetime,
    user_tz: ZoneInfo | None = None,
) -> datetime | None:
    """Parse a natural speech or formatted date string into a timezone-aware UTC datetime.

    Args:
        due_str: Spoken or formatted string (e.g., 'today', 'tomorrow', 'friday',
            'in 3 days', '2026-11-15', 'Nov 15th at 5pm') or None.
        reference_dt: Current baseline datetime.
        user_tz: User's local timezone.

    Returns:
        Timezone-aware datetime in UTC, or None if due_str is empty.

    Raises:
        InvalidInputError: If date cannot be parsed or is in the past.
    """
    if due_str is None or not due_str.strip():
        return None

    tz = user_tz or reference_dt.tzinfo or ZoneInfo("UTC")
    local_now = reference_dt.astimezone(tz)
    raw = due_str.strip().lower()

    # 1. ISO 8601 parsing
    iso_candidate = raw
    if iso_candidate.endswith("z"):
        iso_candidate = iso_candidate[:-1] + "+00:00"
    if " " in iso_candidate and "t" not in iso_candidate:
        iso_candidate = iso_candidate.replace(" ", "T")
    try:
        dt = datetime.fromisoformat(iso_candidate)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz)
        target_utc = dt.astimezone(ZoneInfo("UTC"))
        return target_utc
    except ValueError:
        pass

    # 2. Relative keywords: today, tonight, tomorrow
    if raw in ("today", "tonight"):
        # default to end of day 18:00
        target_local = datetime.combine(local_now.date(), time(18, 0), tzinfo=tz)
        return target_local.astimezone(ZoneInfo("UTC"))

    if raw == "tomorrow":
        target_local = datetime.combine(local_now.date() + timedelta(days=1), time(9, 0), tzinfo=tz)
        return target_local.astimezone(ZoneInfo("UTC"))

    # 3. 'in N days', 'in N hours', 'in N weeks'
    rel_match = re.match(r"^in\s+(\d+)\s+(day|days|hour|hours|week|weeks)$", raw)
    if rel_match:
        qty = int(rel_match.group(1))
        unit = rel_match.group(2)
        if "day" in unit:
            target_local = local_now + timedelta(days=qty)
        elif "week" in unit:
            target_local = local_now + timedelta(weeks=qty)
        elif "hour" in unit:
            target_local = local_now + timedelta(hours=qty)
        return target_local.astimezone(ZoneInfo("UTC"))

    # 4. Day of week ('friday', 'next monday', 'this sunday')
    day_regex = r"^(?:this\s+|next\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)$"
    day_match = re.match(day_regex, raw)
    if day_match:
        target_dow = DAYS_OF_WEEK[day_match.group(1)]
        current_dow = local_now.weekday()
        days_ahead = (target_dow - current_dow) % 7
        if days_ahead == 0:
            days_ahead = 7  # If today is Friday and user says 'friday', schedule next week
        target_date = local_now.date() + timedelta(days=days_ahead)
        target_local = datetime.combine(target_date, time(9, 0), tzinfo=tz)
        return target_local.astimezone(ZoneInfo("UTC"))

    # 5. Month name and day ('November 15', 'Nov 15th', '15th November')
    month_match = re.search(
        r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
        r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
        r"\s+(\d{1,2})(?:st|nd|rd|th)?",
        raw,
    )
    if month_match:
        m_str = month_match.group(1)
        m_num = MONTH_NAMES[m_str[:3]]
        day_num = int(month_match.group(2))
        year = local_now.year
        try:
            target_date = date(year, m_num, day_num)
            if target_date < local_now.date():
                target_date = date(year + 1, m_num, day_num)
            target_local = datetime.combine(target_date, time(9, 0), tzinfo=tz)
            return target_local.astimezone(ZoneInfo("UTC"))
        except ValueError as err:
            msg = f"Invalid date '{due_str}': {err}"
            raise InvalidInputError(msg) from err

    # 6. 'on the 15th', 'on 25th'
    dom_match = re.match(r"^(?:on\s+(?:the\s+)?)?(\d{1,2})(?:st|nd|rd|th)$", raw)
    if dom_match:
        day_num = int(dom_match.group(1))
        year = local_now.year
        month = local_now.month
        try:
            target_date = date(year, month, day_num)
            if target_date < local_now.date():
                # Advance to next month
                month += 1
                if month > 12:
                    month = 1
                    year += 1
                target_date = date(year, month, day_num)
            target_local = datetime.combine(target_date, time(9, 0), tzinfo=tz)
            return target_local.astimezone(ZoneInfo("UTC"))
        except ValueError as err:
            msg = f"Invalid day of month in '{due_str}': {err}"
            raise InvalidInputError(msg) from err

    msg = (
        f"Could not parse due date '{due_str}'. "
        "Try formats like 'tomorrow', 'Friday', or '2026-11-15'."
    )
    raise InvalidInputError(msg)


def format_tasks_spoken(
    tasks: list[dict[str, Any]],
    list_name: str | None = None,
    user_tz: ZoneInfo | None = None,
) -> str:
    """Format a list of tasks into a natural, concise spoken summary under 300 characters."""
    if not tasks:
        target = f"in your {list_name} list" if list_name else "on your list"
        return f"You have no pending tasks {target}."

    count = len(tasks)
    header = f"You have {count} pending task{'s' if count > 1 else ''}"
    if list_name and list_name != "inbox":
        header += f" in {list_name}"
    header += ":"

    items: list[str] = []
    ordinals = ["First", "Second", "Third", "Fourth", "Fifth"]

    for i, t in enumerate(tasks[:3]):
        ord_name = ordinals[i] if i < len(ordinals) else f"Number {i + 1}"
        title = t.get("title", "Untitled task")
        due = t.get("due_at")

        item_str = f"{ord_name}, {title}"
        if t.get("priority") == "high":
            item_str += ", high priority"
        if due:
            if isinstance(due, str):
                try:
                    dt = datetime.fromisoformat(due)
                except ValueError:
                    dt = None
            else:
                dt = due

            if dt and user_tz:
                dt_local = dt.astimezone(user_tz)
                item_str += f", due {dt_local.strftime('%A, %b %d')}"
            elif dt:
                item_str += f", due {dt.strftime('%A, %b %d')}"

        items.append(item_str)

    summary = f"{header} {'. '.join(items)}."
    if count > 3:
        summary += f" And {count - 3} more."

    # Guarantee voice length cap
    if len(summary) > 300:
        summary = summary[:296] + "..."

    return summary
