"""Unit tests for tool idempotency wrapper and repository (T1.5)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from sahayak.core.auth.principal import (
    Principal,
    reset_current_principal,
    set_current_principal,
)
from sahayak.core.envelope import ok
from sahayak.core.idempotency import (
    IdempotencyService,
    idempotent,
    set_default_idempotency_service,
)


@pytest.fixture(autouse=True)
def clean_idempotency_service() -> None:
    """Reset idempotency service before each test."""
    service = IdempotencyService()
    set_default_idempotency_service(service)


@pytest.mark.asyncio
async def test_idempotent_decorator_replays_cached_response() -> None:
    """Invoking a tool twice with the same request_id executes logic once and replays result."""
    execution_count = 0

    @idempotent(tool_name="add_points")
    async def add_points(points: int = 10, request_id: str = "") -> dict[str, Any]:
        nonlocal execution_count
        execution_count += 1
        return ok(spoken_summary=f"Added {points}", data={"count": execution_count})

    res1 = await add_points(points=10, request_id="req-123")
    assert res1["ok"] is True
    assert res1["data"]["count"] == 1
    assert execution_count == 1

    # Replay with same request_id
    res2 = await add_points(points=10, request_id="req-123")
    assert res2["ok"] is True
    assert res2["data"]["count"] == 1
    assert execution_count == 1  # Logic was NOT executed a second time

    # New request_id executes
    res3 = await add_points(points=10, request_id="req-456")
    assert res3["ok"] is True
    assert res3["data"]["count"] == 2
    assert execution_count == 2


@pytest.mark.asyncio
async def test_different_users_do_not_collide_on_same_request_id() -> None:
    """Two different users using the same request_id are isolated and do not collide."""
    user1_id = uuid.uuid4()
    user2_id = uuid.uuid4()
    execution_count = 0

    @idempotent(tool_name="create_note")
    async def create_note(text: str = "", request_id: str = "") -> dict[str, Any]:
        nonlocal execution_count
        execution_count += 1
        return ok(spoken_summary=text, data={"execution": execution_count})

    # User 1 call
    tok1 = set_current_principal(Principal(user_id=user1_id, anonymous=False))
    try:
        res_u1 = await create_note(text="Note 1", request_id="shared-key")
        assert res_u1["data"]["execution"] == 1
    finally:
        reset_current_principal(tok1)

    # User 2 call with exact same request_id
    tok2 = set_current_principal(Principal(user_id=user2_id, anonymous=False))
    try:
        res_u2 = await create_note(text="Note 2", request_id="shared-key")
        assert res_u2["data"]["execution"] == 2
        assert res_u2["spoken_summary"] == "Note 2"
    finally:
        reset_current_principal(tok2)


@pytest.mark.asyncio
async def test_missing_request_id_runs_without_caching() -> None:
    """Calls without request_id are not cached and execute each time."""
    execution_count = 0

    @idempotent(tool_name="no_key_tool")
    async def no_key_tool(request_id: str = "") -> dict[str, Any]:
        nonlocal execution_count
        execution_count += 1
        return ok(spoken_summary=f"Run {execution_count}", data={"count": execution_count})

    res1 = await no_key_tool()
    assert res1["data"]["count"] == 1

    res2 = await no_key_tool()
    assert res2["data"]["count"] == 2
    assert execution_count == 2
