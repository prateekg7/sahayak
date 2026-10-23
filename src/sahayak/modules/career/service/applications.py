"""ApplicationService managing job application tracking and follow-up deadlines (T8.2)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sahayak.core.db.session import UnitOfWork
from sahayak.core.errors import InvalidInputError, NotFoundError
from sahayak.modules.career.adapters.applications import SQLAlchemyApplicationRepository
from sahayak.modules.career.domain.applications import (
    VALID_STATUSES,
    format_pipeline_summary,
    normalize_status,
    parse_follow_up_date,
)
from sahayak.modules.career.domain.rubric import sanitize_spoken_text


class ApplicationService:
    """Service orchestrating job application tracking with transactional Unit of Work."""

    def __init__(
        self,
        session_factory: Any,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.clock = clock or (lambda: datetime.now(UTC))

    def _now(self) -> datetime:
        dt = self.clock()
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)

    async def add_application(
        self,
        *,
        user_id: uuid.UUID,
        company: str,
        role: str,
        status: str = "applied",
        follow_up_at_str: str | None = None,
        notes: str | None = None,
    ) -> tuple[dict[str, Any], str, list[str]]:
        """Track a new job application."""
        if not company or not company.strip():
            raise InvalidInputError("Company name is required to track a job application.")
        if not role or not role.strip():
            raise InvalidInputError("Job role or title is required to track an application.")

        norm_status = normalize_status(status)
        if norm_status not in VALID_STATUSES:
            raise InvalidInputError(
                f"Invalid status '{status}'. Valid statuses are: "
                f"{', '.join(sorted(VALID_STATUSES))}."
            )

        now = self._now()
        follow_up_dt = parse_follow_up_date(follow_up_at_str, base_time=now)

        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyApplicationRepository(uow.session)
            app = await repo.create_application(
                user_id=user_id,
                company=company.strip(),
                role=role.strip(),
                status=norm_status,
                follow_up_at=follow_up_dt,
                notes=notes.strip() if notes else None,
            )
            app_id = str(app.id)
            await uow.session.commit()

        follow_phrase = ""
        if follow_up_dt:
            date_str = follow_up_dt.strftime("%B %d")
            follow_phrase = f" Follow-up deadline set for {date_str}."

        spoken = sanitize_spoken_text(
            f"Added application for {role.strip()} at {company.strip()} "
            f"marked as {norm_status}.{follow_phrase}"
        )
        data = {
            "application_id": app_id,
            "company": company.strip(),
            "role": role.strip(),
            "status": norm_status,
            "follow_up_at": follow_up_dt.isoformat() if follow_up_dt else None,
            "notes": notes.strip() if notes else None,
        }
        next_actions = [
            "application_tracker(action='list')",
            "application_tracker(action='due_followups')",
        ]
        return data, spoken, next_actions

    async def update_status(
        self,
        *,
        user_id: uuid.UUID,
        application_id_str: str,
        status: str,
        notes: str | None = None,
    ) -> tuple[dict[str, Any], str, list[str]]:
        """Update interview pipeline status for a tracked application."""
        try:
            app_id = uuid.UUID(application_id_str)
        except (ValueError, TypeError):
            raise InvalidInputError("Please provide a valid application ID to update.") from None

        norm_status = normalize_status(status)
        if norm_status not in VALID_STATUSES:
            raise InvalidInputError(
                f"Invalid status '{status}'. Valid statuses are: "
                f"{', '.join(sorted(VALID_STATUSES))}."
            )

        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyApplicationRepository(uow.session)
            app = await repo.update_status(
                user_id=user_id,
                application_id=app_id,
                status=norm_status,
                notes=notes.strip() if notes else None,
            )
            if not app:
                raise NotFoundError("Application not found. Want to check your application list?")
            company = app.company
            role = app.role
            await uow.session.commit()

        spoken = sanitize_spoken_text(f"Updated {company} application for {role} to {norm_status}.")
        data = {
            "application_id": str(app_id),
            "company": company,
            "role": role,
            "status": norm_status,
        }
        next_actions = [
            "application_tracker(action='list')",
            f"application_tracker(action='update_status', application_id='{app_id}')",
        ]
        return data, spoken, next_actions

    async def list_applications(
        self,
        *,
        user_id: uuid.UUID,
        status: str | None = None,
        limit: int = 10,
    ) -> tuple[dict[str, Any], str, list[str]]:
        """List active or filtered applications and return voice pipeline summary."""
        limit = max(1, min(50, limit))
        norm_status = normalize_status(status) if status else None

        now = self._now()
        cutoff = now + timedelta(days=2)

        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyApplicationRepository(uow.session)
            apps = await repo.list_applications(user_id=user_id, status=norm_status, limit=limit)
            due_apps = await repo.list_due_followups(user_id=user_id, before_time=cutoff, limit=5)

            app_dicts: list[dict[str, Any]] = [a.to_dict() for a in apps]
            spoken = format_pipeline_summary(app_dicts, due_count=len(due_apps))

        data = {
            "applications": app_dicts,
            "total_returned": len(app_dicts),
            "filter_status": norm_status,
        }
        next_actions = [
            "application_tracker(action='add')",
            "application_tracker(action='due_followups')",
        ]
        return data, spoken, next_actions

    async def list_due_followups(
        self,
        *,
        user_id: uuid.UUID,
        limit: int = 10,
    ) -> tuple[dict[str, Any], str, list[str]]:
        """List applications with upcoming follow-up deadlines."""
        limit = max(1, min(50, limit))
        now = self._now()
        cutoff = now + timedelta(days=7)

        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyApplicationRepository(uow.session)
            due_apps = await repo.list_due_followups(
                user_id=user_id,
                before_time=cutoff,
                limit=limit,
            )
            app_dicts: list[dict[str, Any]] = [a.to_dict() for a in due_apps]

        if not app_dicts:
            spoken = "You have no upcoming job application follow-up deadlines for the next 7 days."
        else:
            first = app_dicts[0]
            spoken = sanitize_spoken_text(
                f"You have {len(app_dicts)} follow-up deadline{'s' if len(app_dicts) > 1 else ''}. "
                f"Next is {first['company']} for {first['role']}."
            )

        data = {
            "due_followups": app_dicts,
            "count": len(app_dicts),
        }
        next_actions = [
            "application_tracker(action='list')",
            "application_tracker(action='add')",
        ]
        return data, spoken, next_actions

    async def delete_application(
        self,
        *,
        user_id: uuid.UUID,
        application_id_str: str,
    ) -> tuple[dict[str, Any], str, list[str]]:
        """Delete a tracked application."""
        try:
            app_id = uuid.UUID(application_id_str)
        except (ValueError, TypeError):
            raise InvalidInputError("Please provide a valid application ID to delete.") from None

        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyApplicationRepository(uow.session)
            deleted = await repo.delete_application(user_id=user_id, application_id=app_id)
            if not deleted:
                raise NotFoundError("Application not found.")
            await uow.session.commit()

        spoken = "Deleted job application from your tracker."
        data = {"application_id": str(app_id), "deleted": True}
        next_actions = ["application_tracker(action='list')"]
        return data, spoken, next_actions
