"""Integration tests for transactional outbox and event dispatcher on PostgreSQL (T1.6)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.config import get_settings
from sahayak.core.db.session import UnitOfWork
from sahayak.core.events import (
    DeadLetterEventRecord,
    DomainEvent,
    EventDispatcher,
    OutboxEventRecord,
    idempotent_handler,
    publish,
)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_event_published_in_rolled_back_transaction_is_never_delivered() -> None:
    """Outbox event written in a rolled-back transaction never appears in DB or dispatch."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("PostgreSQL database is not accessible")

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    dispatcher = EventDispatcher(session_factory=session_factory)

    # Drain any pre-existing pending events from prior test runs
    await dispatcher.dispatch_pending()

    received_events: list[DomainEvent] = []
    dispatcher.subscribe("quiz.aborted", lambda e: received_events.append(e))

    event_id = uuid.uuid4()

    # Roll back transaction explicitly
    try:
        async with UnitOfWork(session_factory) as uow:
            publish(
                session=uow.session,
                aggregate="quiz",
                type="quiz.aborted",
                payload={"quiz_id": "q-aborted"},
                event_id=event_id,
            )
            raise RuntimeError("Force rollback")
    except RuntimeError:
        pass

    # Verify event is not in outbox table
    async with UnitOfWork(session_factory) as uow:
        result = await uow.session.execute(
            select(OutboxEventRecord).where(OutboxEventRecord.id == event_id)
        )
        assert result.scalar_one_or_none() is None

    # Run dispatcher — nothing should be dispatched
    dispatched = await dispatcher.dispatch_pending()
    assert dispatched == 0
    assert len(received_events) == 0

    await engine.dispose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_outbox_dispatch_success_and_idempotent_handler() -> None:
    """Committed event is dispatched, marked processed, and handles duplicates safely."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("PostgreSQL database is not accessible")

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    dispatcher = EventDispatcher(session_factory=session_factory)

    handle_count = 0

    @idempotent_handler()
    async def sample_subscriber(event: DomainEvent) -> None:
        nonlocal handle_count
        handle_count += 1

    event_type = f"quiz.finished.{uuid.uuid4()}"
    dispatcher.subscribe(event_type, sample_subscriber)

    event_id = uuid.uuid4()

    # Commit event
    async with UnitOfWork(session_factory) as uow:
        publish(
            session=uow.session,
            aggregate="quiz",
            type=event_type,
            payload={"score": 100},
            event_id=event_id,
        )
        await uow.session.commit()

    # First dispatch batch
    dispatched = await dispatcher.dispatch_pending()
    assert dispatched >= 1
    assert handle_count == 1

    # Verify processed_at is set in database
    async with UnitOfWork(session_factory) as uow:
        record = (
            await uow.session.execute(
                select(OutboxEventRecord).where(OutboxEventRecord.id == event_id)
            )
        ).scalar_one()
        assert record.processed_at is not None

    # Dispatching again finds 0 pending events for this ID
    dispatched_again = await dispatcher.dispatch_pending()
    assert dispatched_again == 0

    # Deliver duplicate manually to subscriber: should be a no-op
    test_event = DomainEvent(
        id=event_id,
        aggregate="quiz",
        type=event_type,
        payload={"score": 100},
        created_at=record.created_at,
    )
    await sample_subscriber(test_event)
    assert handle_count == 1  # Duplicate was rejected harmlessly

    await engine.dispose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_handler_failure_retries_and_dead_letters() -> None:
    """Repeated handler failure increments retry_count and moves to dead_letter_events."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("PostgreSQL database is not accessible")

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    dispatcher = EventDispatcher(session_factory=session_factory, max_retries=3)

    fail_type = f"failing.event.{uuid.uuid4()}"

    def failing_subscriber(event: DomainEvent) -> None:
        raise ValueError("Simulated subscriber crash")

    dispatcher.subscribe(fail_type, failing_subscriber)

    event_id = uuid.uuid4()

    # Commit event
    async with UnitOfWork(session_factory) as uow:
        publish(
            session=uow.session,
            aggregate="test",
            type=fail_type,
            payload={"fail": True},
            event_id=event_id,
        )
        await uow.session.commit()

    # Dispatch attempt 1: failure (retry=1)
    await dispatcher.dispatch_pending()
    async with UnitOfWork(session_factory) as uow:
        rec1 = (
            await uow.session.execute(
                select(OutboxEventRecord).where(OutboxEventRecord.id == event_id)
            )
        ).scalar_one()
        assert rec1.retry_count == 1
        assert rec1.processed_at is None
        assert "ValueError" in (rec1.last_error or "")

    # Dispatch attempt 2: failure (retry=2)
    await dispatcher.dispatch_pending()
    async with UnitOfWork(session_factory) as uow:
        rec2 = (
            await uow.session.execute(
                select(OutboxEventRecord).where(OutboxEventRecord.id == event_id)
            )
        ).scalar_one()
        assert rec2.retry_count == 2
        assert rec2.processed_at is None

    # Dispatch attempt 3: failure reaches max_retries (3) -> Dead lettered!
    await dispatcher.dispatch_pending()
    async with UnitOfWork(session_factory) as uow:
        rec3 = (
            await uow.session.execute(
                select(OutboxEventRecord).where(OutboxEventRecord.id == event_id)
            )
        ).scalar_one()
        assert rec3.retry_count == 3
        # Marked processed so it will not be retried in normal loop
        assert rec3.processed_at is not None

        # Verify dead letter entry exists
        dl = (
            await uow.session.execute(
                select(DeadLetterEventRecord).where(
                    DeadLetterEventRecord.outbox_event_id == event_id
                )
            )
        ).scalar_one_or_none()
        assert dl is not None
        assert dl.type == fail_type
        assert "ValueError" in dl.error

    await engine.dispose()
