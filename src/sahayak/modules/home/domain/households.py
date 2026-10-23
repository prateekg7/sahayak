"""Household domain logic: invite code generation, role assertion, spoken formatting (T9.1)."""

from __future__ import annotations

import re
import secrets
from enum import StrEnum

from sahayak.core.errors import InvalidInputError

# Unambiguous characters for easy speech recognition and reading (no 0/O, 1/I)
INVITE_CHARSET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
INVITE_CODE_LENGTH = 6


class HouseholdRole(StrEnum):
    """Household membership roles."""

    OWNER = "owner"
    MEMBER = "member"


def generate_invite_code(length: int = INVITE_CODE_LENGTH) -> str:
    """Generate a random unambiguous alphanumeric invite code."""
    return "".join(secrets.choice(INVITE_CHARSET) for _ in range(length))


def normalize_household_name(name: str) -> str:
    """Normalize and validate a household name."""
    cleaned = name.strip()
    if not cleaned:
        raise InvalidInputError("Household name cannot be empty.")
    if len(cleaned) > 128:
        raise InvalidInputError("Household name cannot exceed 128 characters.")
    return cleaned


def normalize_invite_code(code: str) -> str:
    """Normalize and validate an invite code string."""
    cleaned = code.strip().upper()
    if not cleaned:
        raise InvalidInputError("Invite code cannot be empty.")
    if len(cleaned) < 4 or len(cleaned) > 16:
        raise InvalidInputError("Invite code must be between 4 and 16 characters.")
    return cleaned


def sanitize_spoken_text(text: str) -> str:
    """Ensure spoken text complies with voice UX rules: <= 300 chars, no markdown or emojis."""
    clean = re.sub(r"[\*#_`~<>{}\[\]\(\)]", "", text)
    clean = re.sub(r'["\']', "", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    if len(clean) > 300:
        clean = clean[:297].rstrip() + "..."
    return clean


def format_household_created_spoken(name: str, invite_code: str) -> str:
    """Format spoken response when a new household is created."""
    spaced_code = " ".join(list(invite_code))
    text = (
        f"Created household {name}. Your family invite code is {spaced_code}. "
        "Share this code to let members join."
    )
    return sanitize_spoken_text(text)


def format_joined_spoken(name: str) -> str:
    """Format spoken response when a user joins a household."""
    text = f"You joined {name}. You can now view and share lists and chores."
    return sanitize_spoken_text(text)


def format_members_spoken(name: str, count: int) -> str:
    """Format spoken summary of household members."""
    suffix = "s" if count != 1 else ""
    text = f"{name} currently has {count} member{suffix}."
    return sanitize_spoken_text(text)
