"""Domain logic for household chores, fair rotation, and voice formatters (T9.3)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sahayak.core.errors import InvalidInputError
from sahayak.modules.home.domain.households import sanitize_spoken_text

VALID_FREQUENCIES = {"daily", "weekly", "biweekly", "monthly"}


def normalize_chore_title(title: str) -> str:
    """Normalize chore title and validate length."""
    cleaned = title.strip()
    if not cleaned:
        raise InvalidInputError("Chore title cannot be empty.")
    if len(cleaned) > 256:
        raise InvalidInputError("Chore title cannot exceed 256 characters.")
    return cleaned.title()


def normalize_frequency(freq: str | None) -> str:
    """Normalize and validate chore repetition frequency."""
    if not freq or not freq.strip():
        return "weekly"
    f = freq.strip().lower()
    if f not in VALID_FREQUENCIES:
        raise InvalidInputError(
            f"Invalid frequency '{freq}'. Supported frequencies: daily, weekly, biweekly, monthly."
        )
    return f


def compute_next_due_date(frequency: str, base_time: datetime | None = None) -> datetime:
    """Compute the next due timestamp based on chore frequency."""
    now = base_time or datetime.now(UTC)
    freq = frequency.lower()
    if freq == "daily":
        return now + timedelta(days=1)
    if freq == "biweekly":
        return now + timedelta(days=14)
    if freq == "monthly":
        return now + timedelta(days=30)
    # Default: weekly
    return now + timedelta(days=7)


def compute_next_chore_turn(
    rotation_members: list[str],
    current_index: int,
) -> tuple[str | None, int]:
    """Compute who has the next turn in a fair round-robin rotation.

    Returns (next_member_id_or_name, updated_rotation_index).
    """
    if not rotation_members:
        return None, current_index

    clean_members = [m.strip() for m in rotation_members if m and m.strip()]
    if not clean_members:
        return None, current_index

    next_index = (current_index + 1) % len(clean_members)
    next_member = clean_members[next_index]
    return next_member, next_index


def format_chore_added_spoken(
    title: str,
    assigned_name: str | None,
    frequency: str,
) -> str:
    """Voice summary when a chore is created."""
    assign_part = f"assigned to {assigned_name}" if assigned_name else "with open assignment"
    return sanitize_spoken_text(f"Added {title} as a {frequency} chore {assign_part}.")


def format_whose_turn_spoken(
    title: str,
    assigned_name: str | None,
    next_due: datetime | None = None,
) -> str:
    """Voice summary for 'whose turn' queries."""
    due_str = f" due on {next_due.strftime('%A, %B %d')}" if next_due else ""
    if assigned_name:
        return sanitize_spoken_text(f"It is {assigned_name}'s turn for {title}{due_str}.")
    return sanitize_spoken_text(f"{title} is currently unassigned{due_str}.")


def format_chore_completed_spoken(
    title: str,
    next_name: str | None,
) -> str:
    """Voice summary when a chore is completed and rotated."""
    if next_name:
        return sanitize_spoken_text(f"Marked {title} as complete. Next up is {next_name}.")
    return sanitize_spoken_text(f"Marked {title} as complete.")


def format_chores_list_spoken(chores: list[dict[str, Any]]) -> str:
    """Voice summary of household chores."""
    if not chores:
        return sanitize_spoken_text("There are no chores scheduled for your household.")

    count = len(chores)
    entries: list[str] = []
    for c in chores[:4]:
        title = c.get("title", "Chore")
        assigned = c.get("assigned_name") or "unassigned"
        entries.append(f"{title} for {assigned}")

    summary = ", ".join(entries)
    more = f" and {count - 4} more" if count > 4 else ""
    suffix = "s" if count != 1 else ""
    return sanitize_spoken_text(f"You have {count} chore{suffix}: {summary}{more}.")
