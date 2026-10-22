"""Unit tests for domain events, outbox models, and dispatching (T1.6)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from sahayak.core.events import (
    DomainEvent,
    EventDispatcher,
    IdempotentHandler,
    idempotent_handler,
    publish,
)
from sahayak.core.module import ModuleRegistry


@pytest.mark.asyncio
async def test_idempotent_handler_deduplicates_event_deliveries() -> None:
    """Invoking an idempotent handler twice with the same event ID runs logic only once."""
    call_count = 0

    @idempotent_handler()
    async def sample_handler(event: DomainEvent) -> None:
        nonlocal call_count
        call_count += 1

    event_id = uuid.uuid4()
    event = DomainEvent(
        id=event_id,
        aggregate="quiz",
        type="quiz.finished",
        payload={"score": 10},
        created_at=datetime.now(UTC),
    )

    # First delivery
    await sample_handler(event)
    assert call_count == 1
    assert isinstance(sample_handler, IdempotentHandler)
    assert event_id in sample_handler.processed_ids

    # Duplicate delivery (same event ID)
    await sample_handler(event)
    assert call_count == 1  # Unchanged!

    # New event ID
    event2 = DomainEvent(
        id=uuid.uuid4(),
        aggregate="quiz",
        type="quiz.finished",
        payload={"score": 20},
        created_at=datetime.now(UTC),
    )
    await sample_handler(event2)
    assert call_count == 2


@pytest.mark.asyncio
async def test_publish_creates_outbox_record_on_session() -> None:
    """Publish function adds OutboxEventRecord to the session without auto-committing."""
    session = MagicMock()
    event_id = uuid.uuid4()

    event = publish(
        session=session,
        aggregate="flashcard",
        type="flashcard.graded",
        payload={"card_id": "c1", "rating": "good"},
        event_id=event_id,
    )

    assert event.id == event_id
    assert event.aggregate == "flashcard"
    assert event.type == "flashcard.graded"
    assert event.payload == {"card_id": "c1", "rating": "good"}

    # Assert that session.add was called with OutboxEventRecord
    session.add.assert_called_once()
    added_record = session.add.call_args[0][0]
    assert added_record.id == event_id
    assert added_record.aggregate == "flashcard"
    assert added_record.type == "flashcard.graded"


@pytest.mark.asyncio
async def test_dispatcher_delivers_to_type_and_wildcard_subscribers() -> None:
    """Dispatcher invokes both type-specific, wildcard, and module listeners."""
    received_specific: list[DomainEvent] = []
    received_wildcard: list[DomainEvent] = []
    received_module: list[DomainEvent] = []

    mock_module = MagicMock()
    mock_module.name = "mock_mod"
    mock_module.on_event = MagicMock(side_effect=lambda e: received_module.append(e))

    registry = ModuleRegistry()
    registry.register(mock_module)

    dispatcher = EventDispatcher(session_factory=MagicMock(), registry=registry)
    dispatcher.subscribe("quiz.finished", lambda e: received_specific.append(e))
    dispatcher.subscribe("*", lambda e: received_wildcard.append(e))

    event = DomainEvent(
        id=uuid.uuid4(),
        aggregate="quiz",
        type="quiz.finished",
        payload={"score": 5},
        created_at=datetime.now(UTC),
    )

    await dispatcher.dispatch_event(event)

    assert len(received_specific) == 1
    assert len(received_wildcard) == 1
    assert len(received_module) == 1
    assert received_specific[0].id == event.id
    assert received_wildcard[0].id == event.id
    assert received_module[0].id == event.id


@pytest.mark.asyncio
async def test_dispatcher_run_loop_stops_on_event() -> None:
    """Dispatcher loop can be stopped cleanly via stop_event."""
    dispatcher = EventDispatcher(session_factory=MagicMock())
    dispatcher.dispatch_pending = AsyncMock(return_value=0)  # type: ignore[method-assign]

    import asyncio

    stop_event = asyncio.Event()
    stop_event.set()

    # Should exit immediately without blocking
    await dispatcher.run_loop(poll_interval=0.01, stop_event=stop_event)
