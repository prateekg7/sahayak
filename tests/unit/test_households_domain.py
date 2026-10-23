"""Unit tests for home module domain logic (T9.1)."""

from __future__ import annotations

import pytest

from sahayak.core.errors import InvalidInputError
from sahayak.modules.home.domain.households import (
    INVITE_CHARSET,
    format_household_created_spoken,
    format_joined_spoken,
    format_members_spoken,
    generate_invite_code,
    normalize_household_name,
    normalize_invite_code,
    sanitize_spoken_text,
)


def test_generate_invite_code() -> None:
    code = generate_invite_code()
    assert len(code) == 6
    assert code.isupper()
    for char in code:
        assert char in INVITE_CHARSET

    # Test uniqueness across samples
    samples = {generate_invite_code() for _ in range(50)}
    assert len(samples) == 50


def test_normalize_household_name() -> None:
    assert normalize_household_name("  Baker Street Family  ") == "Baker Street Family"

    with pytest.raises(InvalidInputError):
        normalize_household_name("   ")

    with pytest.raises(InvalidInputError):
        normalize_household_name("a" * 129)


def test_normalize_invite_code() -> None:
    assert normalize_invite_code("  h7k9m2 ") == "H7K9M2"

    with pytest.raises(InvalidInputError):
        normalize_invite_code("   ")

    with pytest.raises(InvalidInputError):
        normalize_invite_code("abc")  # too short


def test_voice_spoken_formatters() -> None:
    created = format_household_created_spoken("Baker Street", "H7K9M2")
    assert len(created) <= 300
    assert "Baker Street" in created
    assert "H 7 K 9 M 2" in created
    assert "*" not in created
    assert "#" not in created

    joined = format_joined_spoken("Baker Street")
    assert len(joined) <= 300
    assert "You joined Baker Street" in joined

    members_single = format_members_spoken("Baker Street", 1)
    assert "1 member." in members_single

    members_multi = format_members_spoken("Baker Street", 3)
    assert "3 members." in members_multi


def test_sanitize_spoken_text() -> None:
    raw = "Here is **bold** text with `code` and #hashtag."
    sanitized = sanitize_spoken_text(raw)
    assert "*" not in sanitized
    assert "`" not in sanitized
    assert "#" not in sanitized
