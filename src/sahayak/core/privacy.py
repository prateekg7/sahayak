"""Privacy orchestration service for user data export and deletion (T1.8)."""

from __future__ import annotations

import inspect
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func

from sahayak.core.audit import AuditLogger
from sahayak.core.db.session import SessionFactory, UnitOfWork
from sahayak.core.errors import NotFoundError
from sahayak.core.idempotency import IdempotencyRecord
from sahayak.core.module import ModuleRegistry, get_registry
from sahayak.shared.users.service import UserService

logger = logging.getLogger(__name__)


class PrivacyCoordinator:
    """Orchestrates privacy compliance operations across all platform modules."""

    def __init__(
        self,
        session_factory: SessionFactory,
        user_service: UserService,
        registry: ModuleRegistry | None = None,
        audit_logger: AuditLogger | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._user_service = user_service
        self._registry = registry or get_registry()
        self._audit = audit_logger or AuditLogger()

    def _normalize_uuid(self, user_id: uuid.UUID | str) -> uuid.UUID:
        if isinstance(user_id, uuid.UUID):
            return user_id
        try:
            return uuid.UUID(str(user_id))
        except ValueError as exc:
            msg = f"Invalid user_id format: {user_id}"
            raise NotFoundError(msg) from exc

    async def export_user_data(
        self,
        user_id: uuid.UUID | str,
        client_ip: str | None = None,
    ) -> dict[str, Any]:
        """Export all data owned by a user across core and feature modules.

        Returns a standardized, JSON-serializable bundle.
        """
        uid = self._normalize_uuid(user_id)
        user = await self._user_service.get_by_id(uid)
        if user is None:
            msg = f"User {uid} not found"
            raise NotFoundError(msg)

        identities = await self._user_service.get_identities(uid)

        # 1. Collect module-specific data
        module_data: dict[str, Any] = {}
        for mod in self._registry.modules.values():
            try:
                res = mod.export_user_data(str(uid))
                if inspect.isawaitable(res):
                    res = await res
                module_data[mod.name] = res
            except Exception as exc:
                logger.error("export_failed module=%s user_id=%s: %s", mod.name, uid, exc)
                module_data[mod.name] = {"error": f"Failed to export: {exc}"}

        # 2. Collect audit history
        async with UnitOfWork(self._session_factory) as uow:
            audit_records = await self._audit.list_for_user(uow.session, uid)
            audit_trail = [
                {
                    "action": rec.action,
                    "resource": rec.resource,
                    "created_at": rec.created_at.isoformat(),
                }
                for rec in audit_records
            ]

            # Log this export event
            await self._audit.log(
                uow.session,
                action="user.export",
                resource=f"user:{uid}",
                user_id=uid,
                client_ip=client_ip,
            )
            await uow.session.commit()

        return {
            "exported_at": datetime.now(UTC).isoformat(),
            "user_id": str(uid),
            "profile": {
                "id": str(user.id),
                "locale": user.locale,
                "timezone": user.timezone,
                "created_at": user.created_at.isoformat() if user.created_at else None,
            },
            "identities": [
                {
                    "issuer": ident.issuer,
                    "subject": ident.subject,
                    "created_at": ident.created_at.isoformat() if ident.created_at else None,
                }
                for ident in identities
            ],
            "modules": module_data,
            "audit_trail": audit_trail,
        }

    async def delete_user_data(
        self,
        user_id: uuid.UUID | str,
        client_ip: str | None = None,
    ) -> None:
        """Permanently erase all user data across all schemas and modules.

        Following execution, no rows referencing the user remain in the database.
        """
        uid = self._normalize_uuid(user_id)
        user = await self._user_service.get_by_id(uid)
        if user is None:
            msg = f"User {uid} not found"
            raise NotFoundError(msg)

        # 1. Instruct each module to delete user data
        for mod in self._registry.modules.values():
            try:
                res = mod.delete_user_data(str(uid))
                if inspect.isawaitable(res):
                    await res
            except Exception as exc:
                logger.error("module_delete_failed module=%s user_id=%s: %s", mod.name, uid, exc)
                raise

        # 2. Erase from core tables
        async with UnitOfWork(self._session_factory) as uow:
            # Delete idempotency records
            await uow.session.execute(
                delete(IdempotencyRecord).where(IdempotencyRecord.user_id == uid)
            )

            # Record anonymized audit log before erasing user row
            await self._audit.log(
                uow.session,
                action="user.delete",
                resource=f"user:{uid}",
                user_id=None,
                client_ip=client_ip,
            )

            # Hard delete user (cascades to identities, audit_log user_id set to null)
            await self._user_service.hard_delete_user(uid, session=uow.session)
            await uow.session.commit()

        logger.info("user_data_deleted user_id=%s", uid)


class RetentionManager:
    """Scheduled cleanup of historical and ephemeral data."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory
        self._audit = AuditLogger()

    async def run_cleanup(self, audit_days: int = 90) -> dict[str, int]:
        """Prune expired idempotency keys and stale audit log entries."""
        from sqlalchemy.engine import CursorResult

        counts = {"pruned_idempotency_keys": 0, "pruned_audit_logs": 0}

        async with UnitOfWork(self._session_factory) as uow:
            # 1. Prune expired idempotency keys
            stmt = delete(IdempotencyRecord).where(IdempotencyRecord.expires_at < func.now())
            idemp_res = await uow.session.execute(stmt)
            if isinstance(idemp_res, CursorResult):
                counts["pruned_idempotency_keys"] = int(idemp_res.rowcount)

            # 2. Prune old audit logs
            counts["pruned_audit_logs"] = await self._audit.prune(
                uow.session, older_than_days=audit_days
            )

            await uow.session.commit()

        return counts
