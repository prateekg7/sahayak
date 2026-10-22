"""Audit logging for privacy and compliance (T1.8)."""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import DateTime, ForeignKey, String, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from sahayak.core.db.base import Base

logger = logging.getLogger(__name__)


class AuditLogRecord(Base):
    """Immutable audit trail record.

    Stores actions, targeted resources, and anonymized IP hashes.
    Never stores sensitive request payloads, passwords, or PII.
    """

    __tablename__ = "audit_log"
    __table_args__ = {"schema": "core"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("core.users.id", ondelete="SET NULL"),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource: Mapped[str] = mapped_column(String(128), nullable=False)
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class AuditLogger:
    """Records and queries audit events with privacy-preserving anonymization."""

    @staticmethod
    def hash_ip(client_ip: str | None) -> str | None:
        """Hash client IP with SHA-256 to avoid storing raw IP addresses."""
        if not client_ip:
            return None
        return hashlib.sha256(client_ip.strip().encode("utf-8")).hexdigest()

    async def log(
        self,
        session: AsyncSession,
        action: str,
        resource: str,
        user_id: uuid.UUID | None = None,
        client_ip: str | None = None,
    ) -> AuditLogRecord:
        """Create and persist an audit log entry."""
        record = AuditLogRecord(
            id=uuid.uuid4(),
            user_id=user_id,
            action=action,
            resource=resource,
            ip_hash=self.hash_ip(client_ip),
            created_at=datetime.now(UTC),
        )
        session.add(record)
        await session.flush()
        logger.info(
            "audit_event action=%s resource=%s user_id=%s",
            action,
            resource,
            user_id,
        )
        return record

    async def list_for_user(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        limit: int = 100,
    ) -> list[AuditLogRecord]:
        """Fetch audit trail associated with a specific user."""
        stmt = (
            select(AuditLogRecord)
            .where(AuditLogRecord.user_id == user_id)
            .order_by(AuditLogRecord.created_at.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def prune(
        self,
        session: AsyncSession,
        older_than_days: int = 90,
    ) -> int:
        """Remove audit entries older than retention threshold."""
        from sqlalchemy.engine import CursorResult

        cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
        stmt = delete(AuditLogRecord).where(AuditLogRecord.created_at < cutoff)
        result = await session.execute(stmt)
        if isinstance(result, CursorResult):
            return int(result.rowcount)
        return 0
