"""Unit tests for feature flags, user preferences, and admin CLI operations (T13.3)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from scripts.admin import (
    flag_question,
    replay_dead_letter,
    set_feature_flag,
)

from sahayak.core.flags import (
    FeatureFlagStore,
    UserPreferenceService,
    check_feature_flag,
)


@pytest.mark.asyncio
async def test_feature_flag_store_evaluation() -> None:
    """Test global enable/disable, user overrides, and percentage rollout."""
    store = FeatureFlagStore()

    # 1. Global toggle
    store.set_in_memory_flag("beta_search", enabled=False)
    assert await store.is_enabled("beta_search") is False

    store.set_in_memory_flag("beta_search", enabled=True)
    assert await store.is_enabled("beta_search") is True

    # 2. User overrides
    vip_user = uuid.uuid4()
    blocked_user = uuid.uuid4()
    store.set_in_memory_flag(
        "vip_mode",
        enabled=False,
        user_overrides={str(vip_user): True, str(blocked_user): False},
    )
    assert await store.is_enabled("vip_mode", user_id=vip_user) is True
    assert await store.is_enabled("vip_mode", user_id=blocked_user) is False
    assert await store.is_enabled("vip_mode", user_id=uuid.uuid4()) is False

    # 3. Percentage rollout
    store.set_in_memory_flag("gradual_feature", enabled=True, rollout_percentage=50)
    # Rollout must be deterministic for the same user ID
    test_user = uuid.uuid4()
    first_check = await store.is_enabled("gradual_feature", user_id=test_user)
    second_check = await store.is_enabled("gradual_feature", user_id=test_user)
    assert first_check == second_check


@pytest.mark.asyncio
async def test_check_feature_flag_decorator() -> None:
    """Flagged-off tool returns a graceful envelope with error_code='feature_disabled'."""
    store = FeatureFlagStore()
    store.set_in_memory_flag("experimental_tool", enabled=False)

    with patch("sahayak.core.flags.get_feature_flag_store", return_value=store):

        @check_feature_flag("experimental_tool")
        async def sample_tool() -> dict[str, object]:
            return {"ok": True}

        res = await sample_tool()
        assert res.get("ok") is False
        assert res.get("error_code") == "feature_disabled"
        assert "temporarily unavailable" in str(res.get("spoken_summary"))


@pytest.mark.asyncio
async def test_user_preference_service_toggles() -> None:
    """Users can disable and enable modules independently."""
    service = UserPreferenceService()
    test_user = uuid.uuid4()

    assert await service.is_module_enabled(test_user, "finance") is True

    await service.set_module_enabled(test_user, "finance", enabled=False)
    assert await service.is_module_enabled(test_user, "finance") is False
    disabled = await service.get_disabled_modules(test_user)
    assert "finance" in disabled

    await service.set_module_enabled(test_user, "finance", enabled=True)
    assert await service.is_module_enabled(test_user, "finance") is True
    disabled = await service.get_disabled_modules(test_user)
    assert "finance" not in disabled


@pytest.mark.asyncio
async def test_admin_flag_question_and_quarantine() -> None:
    """Admin flag-question increments count and sets quarantined when threshold is reached."""
    session_mock = AsyncMock()
    mock_question = MagicMock()
    mock_question.flag_count = 2
    mock_question.status = "flagged"

    exec_res = MagicMock()
    exec_res.scalars.return_value.first.return_value = mock_question
    session_mock.execute.return_value = exec_res

    qid = uuid.uuid4()
    await flag_question(session_mock, str(qid), reason="inaccurate fact")

    assert mock_question.flag_count == 3
    assert mock_question.status == "quarantined"
    assert session_mock.commit.called
    assert session_mock.add.called  # Audit record added


@pytest.mark.asyncio
async def test_admin_replay_dead_letter() -> None:
    """Admin replay-dead-letter re-inserts into outbox and deletes dead letter record."""
    session_mock = AsyncMock()
    dead_event = MagicMock()
    dead_event.id = uuid.uuid4()
    dead_event.aggregate = "quiz"
    dead_event.type = "quiz.completed"
    dead_event.payload = {"quiz_id": "123"}

    exec_res = MagicMock()
    exec_res.scalars.return_value.all.return_value = [dead_event]
    session_mock.execute.return_value = exec_res

    await replay_dead_letter(session_mock, str(dead_event.id), replay_all=False)

    assert session_mock.add.called  # Re-inserted outbox event + audit log
    assert session_mock.delete.called  # Removed dead letter
    assert session_mock.commit.called


@pytest.mark.asyncio
async def test_admin_set_feature_flag_persists_and_audits() -> None:
    """Admin set-flag updates record and writes audit trail."""
    session_mock = AsyncMock()
    exec_res = MagicMock()
    exec_res.scalars.return_value.first.return_value = None  # New flag
    session_mock.execute.return_value = exec_res

    await set_feature_flag(
        session_mock,
        name="dark_mode",
        enabled=True,
        rollout=80,
        user_override="user-1=true",
    )

    assert session_mock.add.called
    assert session_mock.commit.called
