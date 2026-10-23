"""Unit and integration tests for HouseholdService, HomeAPI, and tenancy isolation (T9.1)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.config import get_settings
from sahayak.core.db.session import UnitOfWork
from sahayak.core.errors import ForbiddenError, NotFoundError
from sahayak.modules.home.api import HomeAPI
from sahayak.modules.home.service.households import HouseholdService
from sahayak.shared.users.models import User


@pytest.mark.asyncio
async def test_household_service_full_tenancy_lifecycle() -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    user_c = uuid.uuid4()  # Non-member

    fixed_now = datetime(2026, 10, 24, 12, 0, 0, tzinfo=UTC)
    service = HouseholdService(session_factory=session_factory, clock=lambda: fixed_now)
    api = HomeAPI(session_factory=session_factory)

    try:
        async with UnitOfWork(session_factory) as uow:
            uow.session.add_all([User(id=user_a), User(id=user_b), User(id=user_c)])
            await uow.session.commit()

        # 1. User A creates household "Baker Street"
        create_data, create_spoken, _ = await service.create_household(
            user_id=user_a,
            name="Baker Street",
        )
        assert create_data["household"]["name"] == "Baker Street"
        assert create_data["membership"]["role"] == "owner"
        assert "Baker Street" in create_spoken
        h_id_str = create_data["household"]["id"]
        h_id = uuid.UUID(h_id_str)
        invite_code = create_data["invite"]["code"]

        # 2. assert_member for creator
        m_a = await service.assert_member(household_id=h_id, user_id=user_a)
        assert m_a.role == "owner"
        await service.assert_member(household_id=h_id, user_id=user_a, required_role="owner")

        # Non-member User B cannot access yet
        with pytest.raises(ForbiddenError):
            await service.assert_member(household_id=h_id, user_id=user_b)

        # 3. User B joins via invite code
        join_data, join_spoken, _ = await service.join_household(
            user_id=user_b,
            invite_code=invite_code,
        )
        assert join_data["membership"]["role"] == "member"
        assert "You joined Baker Street" in join_spoken

        # 4. User C attempting to use the now-used invite code raises NotFoundError
        with pytest.raises(NotFoundError):
            await service.join_household(user_id=user_c, invite_code=invite_code)

        # User A creates a second invite code
        inv2_data, _, _ = await service.create_invite(user_id=user_a, household_id=h_id)
        code2 = inv2_data["invite_code"]

        # User B attempts to join with code2 but is already a member
        rejoin_data, rejoin_spoken, _ = await service.join_household(
            user_id=user_b,
            invite_code=code2,
        )
        assert rejoin_data.get("already_member") is True
        assert "already a member" in rejoin_spoken

        # 5. assert_member for User B passes, but required_role="owner" fails
        m_b = await service.assert_member(household_id=h_id, user_id=user_b)
        assert m_b.role == "member"

        with pytest.raises(ForbiddenError):
            await service.assert_member(household_id=h_id, user_id=user_b, required_role="owner")

        # 6. HomeAPI verify
        api_m = await api.assert_member(household_id=h_id, user_id=user_b)
        assert api_m.role == "member"

        # Non-member User C fails on HomeAPI
        with pytest.raises(ForbiddenError):
            await api.assert_member(household_id=h_id, user_id=user_c)

        # 7. List members
        members_data, members_spoken, _ = await service.list_members(
            user_id=user_a,
            household_id=h_id,
        )
        assert members_data["count"] == 2
        assert "2 members." in members_spoken
        user_ids = [m["user_id"] for m in members_data["members"]]
        assert str(user_a) in user_ids
        assert str(user_b) in user_ids

        # Non-member User C cannot list members
        with pytest.raises(ForbiddenError):
            await service.list_members(user_id=user_c, household_id=h_id)

        # 8. User A generates new invite code
        inv_data, inv_spoken, _ = await service.create_invite(
            user_id=user_a,
            household_id=h_id,
        )
        new_code = inv_data["invite_code"]
        assert len(new_code) == 6
        assert "valid for 48 hours" in inv_spoken

        # Non-member User C cannot generate invite code
        with pytest.raises(ForbiddenError):
            await service.create_invite(user_id=user_c, household_id=h_id)

        # 9. Expired invite test
        expired_service = HouseholdService(
            session_factory=session_factory,
            clock=lambda: fixed_now + timedelta(hours=49),
        )
        with pytest.raises(NotFoundError):
            await expired_service.join_household(user_id=user_c, invite_code=new_code)

        # 10. User B leaves household
        leave_data, leave_spoken, _ = await service.leave_household(
            user_id=user_b,
            household_id=h_id,
        )
        assert leave_data["left"] is True
        assert "You have left Baker Street" in leave_spoken

        # User B is no longer a member
        with pytest.raises(ForbiddenError):
            await service.assert_member(household_id=h_id, user_id=user_b)

        # 11. User A (sole remaining member) leaves household -> household is deleted
        leave_a_data, _, _ = await service.leave_household(
            user_id=user_a,
            household_id=h_id,
        )
        assert leave_a_data["left"] is True
        h_after = await api.get_household(household_id=h_id)
        assert h_after is None
    finally:
        await engine.dispose()
