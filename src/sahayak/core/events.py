"""Domain events and transactional outbox infrastructure (T1.6)."""

from __future__ import annotations

import asyncio
import functools
import inspect
import logging
import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, Text, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from sahayak.core.db.base import Base
from sahayak.core.db.session import SessionFactory, UnitOfWork
from sahayak.core.module import ModuleRegistry, get_registry

logger = logging.getLogger(__name__)


class OutboxEventRecord(Base):
    """Database record for an event to be dispatched asynchronously."""

    __tablename__ = "outbox_events"
    __table_args__ = {"schema": "core"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    aggregate: Mapped[str] = mapped_column(String(128), nullable=False)
    type: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class DeadLetterEventRecord(Base):
    """Database record for events that repeatedly failed dispatch."""

    __tablename__ = "dead_letter_events"
    __table_args__ = {"schema": "core"}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    outbox_event_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    aggregate: Mapped[str] = mapped_column(String(128), nullable=False)
    type: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    error: Mapped[str] = mapped_column(Text, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False)
    failed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


@dataclass(frozen=True)
class DomainEvent:
    """Immutable domain event payload passed to handlers."""

    id: uuid.UUID
    aggregate: str
    type: str
    payload: dict[str, Any]
    created_at: datetime


EventHandler = Callable[[DomainEvent], Coroutine[Any, Any, None] | None]


def publish(
    session: AsyncSession,
    aggregate: str,
    type: str,
    payload: dict[str, Any],
    event_id: uuid.UUID | None = None,
) -> DomainEvent:
    """Publish a domain event within the caller's active database transaction.

    If the caller's transaction is rolled back, the outbox record is not saved,
    guaranteeing atomic outbox publishing.

    Args:
        session: Active SQLAlchemy async session.
        aggregate: Name of the aggregate generating the event (e.g. 'quiz').
        type: Event type name (e.g. 'quiz.finished').
        payload: JSON-serializable event payload.
        event_id: Optional deterministic or pre-generated UUID.

    Returns:
        The generated DomainEvent.
    """
    eid = event_id or uuid.uuid4()
    now = datetime.now(UTC)
    record = OutboxEventRecord(
        id=eid,
        aggregate=aggregate,
        type=type,
        payload=payload,
        created_at=now,
    )
    session.add(record)
    return DomainEvent(
        id=eid,
        aggregate=aggregate,
        type=type,
        payload=payload,
        created_at=now,
    )


class IdempotentHandler:
    """Callable wrapper that drops duplicate event deliveries."""

    def __init__(self, fn: EventHandler, seen: set[uuid.UUID]) -> None:
        self._fn = fn
        self.processed_ids = seen
        functools.update_wrapper(self, fn)

    async def __call__(self, event: DomainEvent) -> None:
        if event.id in self.processed_ids:
            logger.info("event_already_processed event_id=%s type=%s", event.id, event.type)
            return
        res = self._fn(event)
        if inspect.isawaitable(res):
            await res
        self.processed_ids.add(event.id)


def idempotent_handler(
    processed_ids: set[uuid.UUID] | None = None,
) -> Callable[[EventHandler], IdempotentHandler]:
    """Decorator ensuring that duplicate deliveries of the same event ID are no-ops.

    Args:
        processed_ids: Optional shared set tracking processed event UUIDs.

    Returns:
        Wrapped event handler that skips already-processed event IDs.
    """
    seen: set[uuid.UUID] = processed_ids if processed_ids is not None else set()

    def decorator(fn: EventHandler) -> IdempotentHandler:
        return IdempotentHandler(fn, seen)

    return decorator


class EventDispatcher:
    """Dispatches outbox events to registered module listeners and subscribers."""

    def __init__(
        self,
        session_factory: SessionFactory,
        registry: ModuleRegistry | None = None,
        max_retries: int = 3,
    ) -> None:
        self._session_factory = session_factory
        self._registry = registry or get_registry()
        self._max_retries = max_retries
        self._subscribers: dict[str, list[EventHandler]] = {}

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Register a subscriber for a specific event type or '*'."""
        self._subscribers.setdefault(event_type, []).append(handler)

    async def _invoke_handler(self, handler: EventHandler, event: DomainEvent) -> None:
        """Invoke a synchronous or asynchronous event handler."""
        res = handler(event)
        if inspect.isawaitable(res):
            await res

    async def dispatch_event(self, event: DomainEvent) -> None:
        """Deliver an event to registered subscribers and loaded modules."""
        # 1. Type-specific subscribers
        for handler in self._subscribers.get(event.type, []):
            await self._invoke_handler(handler, event)

        # 2. Wildcard subscribers
        for handler in self._subscribers.get("*", []):
            await self._invoke_handler(handler, event)

        # 3. Loaded modules via Module.on_event
        if self._registry is not None:
            for mod in self._registry.modules.values():
                mod.on_event(event)

    async def dispatch_pending(self, batch_size: int = 50) -> int:
        """Fetch and process a batch of unprocessed outbox events.

        Returns:
            Number of events successfully processed in this batch.
        """
        processed_count = 0

        async with UnitOfWork(self._session_factory) as uow:
            # Query pending events locked with SKIP LOCKED
            stmt = (
                select(OutboxEventRecord)
                .where(OutboxEventRecord.processed_at.is_(None))
                .order_by(OutboxEventRecord.created_at.asc())
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            )
            result = await uow.session.execute(stmt)
            records = list(result.scalars().all())

            for record in records:
                event = DomainEvent(
                    id=record.id,
                    aggregate=record.aggregate,
                    type=record.type,
                    payload=record.payload,
                    created_at=record.created_at,
                )

                try:
                    await self.dispatch_event(event)
                    record.processed_at = datetime.now(UTC)
                    processed_count += 1
                except Exception as exc:
                    record.retry_count += 1
                    record.last_error = f"{type(exc).__name__}: {exc}"
                    logger.warning(
                        "event_dispatch_failed event_id=%s retry=%d err=%s",
                        record.id,
                        record.retry_count,
                        record.last_error,
                    )
                    if record.retry_count >= self._max_retries:
                        dead_letter = DeadLetterEventRecord(
                            id=uuid.uuid4(),
                            outbox_event_id=record.id,
                            aggregate=record.aggregate,
                            type=record.type,
                            payload=record.payload,
                            error=record.last_error,
                            retry_count=record.retry_count,
                        )
                        uow.session.add(dead_letter)
                        record.processed_at = datetime.now(UTC)
                        logger.error(
                            "event_dead_lettered event_id=%s after %d retries",
                            record.id,
                            record.retry_count,
                        )

            await uow.session.commit()

        return processed_count

    async def run_loop(
        self,
        poll_interval: float = 1.0,
        stop_event: asyncio.Event | None = None,
    ) -> None:
        """Continuously poll for and dispatch pending outbox events."""
        while stop_event is None or not stop_event.is_set():
            try:
                count = await self.dispatch_pending()
                if count == 0:
                    await asyncio.sleep(poll_interval)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("error_in_event_dispatcher_loop: %s", exc)
                await asyncio.sleep(poll_interval)
