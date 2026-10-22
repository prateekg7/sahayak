"""Unit tests for Principal context and authorization decorators."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from sahayak.core.auth.principal import (
    Principal,
    allow_anonymous,
    get_current_principal,
    requires,
    reset_current_principal,
    set_current_principal,
)
from sahayak.core.envelope import ok


def test_principal_has_scope() -> None:
    """Principal scope checking behaves correctly."""
    user_id = uuid.uuid4()
    p = Principal(
        user_id=user_id,
        scopes=frozenset(["academics.read", "academics.write"]),
        anonymous=False,
    )
    assert p.has_scope("academics.read")
    assert p.has_scope("academics.write")
    assert not p.has_scope("admin")


def test_context_var_management() -> None:
    """Binding and unbinding principals respects ContextVar lifecycle."""
    default = get_current_principal()
    assert default.anonymous is True
    assert default.user_id is None

    new_p = Principal(user_id=uuid.uuid4(), scopes=frozenset(["test"]), anonymous=False)
    tok = set_current_principal(new_p)
    assert get_current_principal() is new_p

    reset_current_principal(tok)
    assert get_current_principal() is default


@pytest.mark.asyncio
async def test_requires_decorator_unauthenticated_returns_auth_required() -> None:
    """Calling a @requires tool anonymously returns auth_required error envelope."""

    @requires(scope="academics.read")
    async def sample_tool() -> dict[str, Any]:
        return ok(spoken_summary="Secret data")

    # In default context, principal is anonymous
    result = await sample_tool()
    assert result["ok"] is False
    assert result["error_code"] == "auth_required"
    assert "Link your account" in result["spoken_summary"]


@pytest.mark.asyncio
async def test_requires_decorator_missing_scope_returns_forbidden() -> None:
    """Calling a @requires tool without the required scope returns forbidden error envelope."""

    @requires(scope="academics.write")
    async def sample_write_tool() -> dict[str, Any]:
        return ok(spoken_summary="Written")

    p = Principal(
        user_id=uuid.uuid4(),
        scopes=frozenset(["academics.read"]),  # missing academics.write
        anonymous=False,
    )
    tok = set_current_principal(p)
    try:
        result = await sample_write_tool()
        assert result["ok"] is False
        assert result["error_code"] == "forbidden"
        assert "don't have permission" in result["spoken_summary"]
    finally:
        reset_current_principal(tok)


@pytest.mark.asyncio
async def test_requires_decorator_authorized_succeeds() -> None:
    """Calling a @requires tool with matching scope executes the function."""

    @requires(scope="academics.read")
    async def sample_read_tool() -> dict[str, Any]:
        return ok(spoken_summary="Read data", data={"content": 123})

    p = Principal(
        user_id=uuid.uuid4(),
        scopes=frozenset(["academics.read"]),
        anonymous=False,
    )
    tok = set_current_principal(p)
    try:
        result = await sample_read_tool()
        assert result["ok"] is True
        assert result["spoken_summary"] == "Read data"
        assert result["data"]["content"] == 123
    finally:
        reset_current_principal(tok)


@pytest.mark.asyncio
async def test_allow_anonymous_decorator_marks_attribute() -> None:
    """@allow_anonymous sets the attribute and executes normally."""

    @allow_anonymous
    async def sample_anon_tool() -> dict[str, Any]:
        return ok(spoken_summary="Public data")

    assert getattr(sample_anon_tool, "_allow_anonymous", False) is True
    result = await sample_anon_tool()
    assert result["ok"] is True
    assert result["spoken_summary"] == "Public data"
