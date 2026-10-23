"""Unit tests for ApplicationService and repository adapter (T8.2)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.config import get_settings
from sahayak.core.db.session import UnitOfWork
from sahayak.core.errors import InvalidInputError, NotFoundError
from sahayak.modules.career.service.applications import ApplicationService
from sahayak.shared.users.models import User


@pytest.mark.asyncio
async def test_application_service_full_lifecycle() -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    user_id = uuid.uuid4()
    fixed_now = datetime(2026, 10, 24, 10, 0, 0, tzinfo=UTC)

    service = ApplicationService(
        session_factory=session_factory,
        clock=lambda: fixed_now,
    )

    try:
        async with UnitOfWork(session_factory) as uow:
            uow.session.add(User(id=user_id))
            await uow.session.commit()

        # 1. Add application with follow-up deadline
        add_data, add_spoken, _ = await service.add_application(
            user_id=user_id,
            company="Google",
            role="Software Engineer",
            status="applied",
            follow_up_at_str="in 3 days",
            notes="Referred by college alumni",
        )
        assert add_data["company"] == "Google"
        assert add_data["role"] == "Software Engineer"
        assert add_data["status"] == "applied"
        assert add_data["follow_up_at"] is not None
        assert "Google" in add_spoken
        app_id = add_data["application_id"]

        # 2. Add second application
        add2_data, _, _ = await service.add_application(
            user_id=user_id,
            company="Stripe",
            role="Backend Engineer",
            status="applied",
        )
        app2_id = add2_data["application_id"]

        # 3. Update status of Google application to interviewing
        upd_data, upd_spoken, _ = await service.update_status(
            user_id=user_id,
            application_id_str=app_id,
            status="interview",
            notes="Passed recruiter screen",
        )
        assert upd_data["status"] == "interviewing"
        assert "interviewing" in upd_spoken

        # 4. List applications
        list_data, list_spoken, _ = await service.list_applications(user_id=user_id)
        assert list_data["total_returned"] == 2
        assert "2 job applications tracked" in list_spoken

        # 5. Filter list by status
        list_filtered, _, _ = await service.list_applications(
            user_id=user_id,
            status="interviewing",
        )
        assert list_filtered["total_returned"] == 1
        assert list_filtered["applications"][0]["company"] == "Google"

        # 6. Check due follow-ups (Google is due in 3 days)
        due_data, due_spoken, _ = await service.list_due_followups(user_id=user_id)
        assert due_data["count"] >= 1
        assert due_data["due_followups"][0]["company"] == "Google"
        assert "Google" in due_spoken

        # 7. Delete Stripe application
        del_data, del_spoken, _ = await service.delete_application(
            user_id=user_id,
            application_id_str=app2_id,
        )
        assert del_data["deleted"] is True

        # Deleting non-existent application raises NotFoundError
        with pytest.raises(NotFoundError):
            await service.delete_application(
                user_id=user_id,
                application_id_str=str(uuid.uuid4()),
            )

        # Updating invalid status raises InvalidInputError
        with pytest.raises(InvalidInputError):
            await service.update_status(
                user_id=user_id,
                application_id_str=app_id,
                status="fake_status",
            )
    finally:
        await engine.dispose()
