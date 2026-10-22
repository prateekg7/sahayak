"""Idempotency framework for mutating MCP tools (T1.5)."""

from __future__ import annotations

import functools
import logging
import uuid
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta
from typing import Any, TypeVar

from sqlalchemy import DateTime, ForeignKey, String, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from sahayak.core.auth.principal import get_current_principal
from sahayak.core.db.base import Base
from sahayak.core.db.session import SessionFactory, UnitOfWork
from sahayak.core.request_id import get_request_id

logger = logging.getLogger(__name__)

T = TypeVar("T")
ToolFunc = Callable[..., Coroutine[Any, Any, dict[str, Any]]]


class IdempotencyRecord(Base):
    """Database model storing tool responses keyed by request_id, tool, and user."""

    __tablename__ = "idempotency_keys"
    __table_args__ = {"schema": "core"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    tool: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("core.users.id", ondelete="CASCADE"),
        nullable=True,
    )
    response: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class IdempotencyRepository:
    """PostgreSQL storage and retrieval for tool idempotency records."""

    async def get(
        self,
        session: AsyncSession,
        tool: str,
        key: str,
        user_id: uuid.UUID | None,
    ) -> dict[str, Any] | None:
        """Fetch cached response if an unexpired record exists."""
        stmt = select(IdempotencyRecord.response).where(
            IdempotencyRecord.tool == tool,
            IdempotencyRecord.key == key,
            IdempotencyRecord.expires_at > func.now(),
        )
        if user_id is not None:
            stmt = stmt.where(IdempotencyRecord.user_id == user_id)
        else:
            stmt = stmt.where(IdempotencyRecord.user_id.is_(None))

        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def store(
        self,
        session: AsyncSession,
        tool: str,
        key: str,
        user_id: uuid.UUID | None,
        response: dict[str, Any],
        ttl_seconds: int = 86400,
    ) -> None:
        """Store response with explicit expiration timestamp."""
        now = datetime.now(UTC)
        record = IdempotencyRecord(
            id=uuid.uuid4(),
            tool=tool,
            key=key,
            user_id=user_id,
            response=response,
            expires_at=now + timedelta(seconds=ttl_seconds),
        )
        session.add(record)
        await session.flush()


class IdempotencyService:
    """Manages transactional idempotency checks and replay."""

    def __init__(
        self,
        session_factory: SessionFactory | None = None,
        repo: IdempotencyRepository | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._repo = repo or IdempotencyRepository()
        self._in_memory_cache: dict[tuple[str, str, uuid.UUID | None], dict[str, Any]] = {}

    async def get(
        self,
        tool: str,
        key: str,
        user_id: uuid.UUID | None,
    ) -> dict[str, Any] | None:
        """Fetch existing response if previously stored and valid."""
        if self._session_factory is not None:
            async with UnitOfWork(self._session_factory) as uow:
                return await self._repo.get(uow.session, tool, key, user_id)
        return self._in_memory_cache.get((tool, key, user_id))

    async def store(
        self,
        tool: str,
        key: str,
        user_id: uuid.UUID | None,
        response: dict[str, Any],
        ttl_seconds: int = 86400,
    ) -> dict[str, Any]:
        """Store response or recover from concurrent insertion race."""
        if self._session_factory is not None:
            async with UnitOfWork(self._session_factory) as uow:
                try:
                    async with uow.session.begin_nested():
                        await self._repo.store(
                            uow.session, tool, key, user_id, response, ttl_seconds
                        )
                        return response
                except IntegrityError:
                    # Winner's record committed during race; fetch and return it
                    winner_resp = await self._repo.get(uow.session, tool, key, user_id)
                    if winner_resp is not None:
                        return winner_resp
                    return response

        self._in_memory_cache[(tool, key, user_id)] = response
        return response


_default_idempotency_service: IdempotencyService | None = None


def set_default_idempotency_service(service: IdempotencyService | None) -> None:
    """Configure the process-wide default idempotency service."""
    global _default_idempotency_service
    _default_idempotency_service = service


def get_default_idempotency_service() -> IdempotencyService:
    """Return the active idempotency service, falling back to in-memory instance."""
    global _default_idempotency_service
    if _default_idempotency_service is None:
        _default_idempotency_service = IdempotencyService()
    return _default_idempotency_service


def idempotent(
    tool_name: str | None = None,
    ttl_seconds: int = 86400,
) -> Callable[[ToolFunc], ToolFunc]:
    """Decorator ensuring that tool executions with identical request_id are idempotent.

    If request_id is supplied and a matching unexpired response exists for
    the active user and tool, the previous response is replayed without
    re-running the underlying tool implementation.
    """

    def decorator(fn: ToolFunc) -> ToolFunc:
        resolved_tool = tool_name or fn.__name__

        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
            request_id = kwargs.get("request_id") or get_request_id()
            if not request_id:
                return await fn(*args, **kwargs)

            principal = get_current_principal()
            user_id = principal.user_id
            service = get_default_idempotency_service()

            cached = await service.get(resolved_tool, request_id, user_id)
            if cached is not None:
                logger.info(
                    "idempotent_replay tool=%s request_id=%s user_id=%s",
                    resolved_tool,
                    request_id,
                    user_id,
                )
                return cached

            # Execute tool logic
            result = await fn(*args, **kwargs)
            return await service.store(resolved_tool, request_id, user_id, result, ttl_seconds)

        return wrapper

    return decorator
