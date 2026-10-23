"""Integration test for home module privacy export and erasure hooks (T9.1)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.config import get_settings
from sahayak.core.db.session import UnitOfWork
from sahayak.core.module import Deps
from sahayak.modules.home.module import module as home_module
from sahayak.modules.home.service.households import HouseholdService
from sahayak.shared.users.models import User


@pytest.mark.asyncio
async def test_home_privacy_export_and_ownership_transfer() -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    user_owner = uuid.uuid4()
    user_member = uuid.uuid4()

    deps = Deps(session_factory=session_factory)
    home_module.register_tools(None, deps=deps)
    service = HouseholdService(session_factory=session_factory)

    try:
        async with UnitOfWork(session_factory) as uow:
            uow.session.add_all([User(id=user_owner), User(id=user_member)])
            await uow.session.commit()

        # 1. User owner creates household and invites member
        create_data, _, _ = await service.create_household(
            user_id=user_owner,
            name="Rose Cottage",
        )
        code = create_data["invite"]["code"]

        await service.join_household(user_id=user_member, invite_code=code)

        # 2. Export user data for owner
        exported_owner = await home_module.export_user_data(str(user_owner))
        assert "households" in exported_owner
        assert len(exported_owner["households"]) == 1
        assert exported_owner["households"][0]["name"] == "Rose Cottage"
        assert len(exported_owner["memberships"]) == 1
        assert exported_owner["memberships"][0]["role"] == "owner"
        assert len(exported_owner["created_invites"]) >= 1

        # 3. Owner requests GDPR erasure -> ownership transfers to member
        await home_module.delete_user_data(str(user_owner))

        # Check owner records deleted
        post_del = await home_module.export_user_data(str(user_owner))
        assert len(post_del.get("households", [])) == 0
        assert len(post_del.get("memberships", [])) == 0
        assert len(post_del.get("created_invites", [])) == 0

        # Check member has now become the owner
        exported_member = await home_module.export_user_data(str(user_member))
        assert len(exported_member["memberships"]) == 1
        assert exported_member["memberships"][0]["role"] == "owner"

        # 4. Member requests GDPR erasure -> household completely deleted
        await home_module.delete_user_data(str(user_member))
        post_del_member = await home_module.export_user_data(str(user_member))
        assert len(post_del_member.get("households", [])) == 0
        assert len(post_del_member.get("memberships", [])) == 0
    finally:
        await engine.dispose()
