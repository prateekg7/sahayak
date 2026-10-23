"""Unit tests for flashcards MCP tool (T3.10)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.auth.principal import (
    Principal,
    reset_current_principal,
    set_current_principal,
)
from sahayak.core.config import get_settings
from sahayak.core.db.session import UnitOfWork
from sahayak.modules.academics.service.flashcards import FlashcardService
from sahayak.modules.academics.tools.flashcards import flashcards, set_flashcard_service
from sahayak.shared.users.models import User


@pytest.fixture
def fake_clock() -> datetime:
    return datetime(2026, 10, 23, 10, 0, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_flashcards_anonymous_call_rejected() -> None:
    """Anonymous invocation returns standard auth_required error envelope."""
    # Reset principal to anonymous
    token = set_current_principal(Principal(anonymous=True, user_id=None))
    try:
        res = await flashcards(action="list_due")
        assert res["ok"] is False
        assert res["error_code"] == "auth_required"
        assert "link your account" in res["spoken_summary"].lower()
    finally:
        reset_current_principal(token)


@pytest.mark.asyncio
async def test_flashcards_add_and_review_flow(fake_clock: datetime) -> None:
    """Authenticated user adds a flashcard and reviews next due card."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    service = FlashcardService(session_factory=session_factory, clock=lambda: fake_clock)
    set_flashcard_service(service)

    user_id = uuid.uuid4()

    async with UnitOfWork(session_factory) as uow:
        uow.session.add(User(id=user_id))

    token = set_current_principal(Principal(anonymous=False, user_id=user_id))
    try:
        # 1. Add card
        add_res = await flashcards(
            action="add",
            front="What is the speed of light?",
            back="Approximately 300,000 km/s",
            deck="Physics",
        )
        assert add_res["ok"] is True
        assert "Added flashcard to Physics" in add_res["spoken_summary"]
        card_data = add_res["data"]["card"]
        card_id = card_data["card_id"]
        assert card_data["front"] == "What is the speed of light?"
        assert card_data["deck"] == "Physics"

        # 2. Review next due
        rev_res = await flashcards(action="review_next", deck="Physics")
        assert rev_res["ok"] is True
        assert "What is the speed of light?" in rev_res["spoken_summary"]
        assert "show answer" in rev_res["spoken_summary"]
        assert rev_res["data"]["card"]["card_id"] == card_id

        # 3. Grade card as good
        grade_res = await flashcards(
            action="grade",
            card_id=card_id,
            rating="good",
        )
        assert grade_res["ok"] is True
        assert "Card graded as good" in grade_res["spoken_summary"]
        assert "1 day" in grade_res["spoken_summary"]
        assert grade_res["data"]["next_review_days"] == 1

        # 4. Review next due after grading - should be caught up
        rev_after = await flashcards(action="review_next", deck="Physics")
        assert rev_after["ok"] is True
        assert "all caught up" in rev_after["spoken_summary"].lower()
        assert rev_after["data"]["total_due"] == 0

        # 5. List due cards
        list_res = await flashcards(action="list_due", deck="Physics")
        assert list_res["ok"] is True
        assert list_res["data"]["total_due"] == 0
    finally:
        reset_current_principal(token)
        set_flashcard_service(None)
        await engine.dispose()


@pytest.mark.asyncio
async def test_flashcards_validation_errors() -> None:
    """Missing or invalid action inputs return invalid_input error envelope."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    service = FlashcardService(session_factory=session_factory)
    set_flashcard_service(service)

    user_id = uuid.uuid4()
    token = set_current_principal(Principal(anonymous=False, user_id=user_id))
    try:
        # Missing front for add
        r1 = await flashcards(action="add", front="", back="some back")
        assert r1["ok"] is False
        assert r1["error_code"] == "invalid_input"

        # Missing back for add
        r2 = await flashcards(action="add", front="some front", back="")
        assert r2["ok"] is False
        assert r2["error_code"] == "invalid_input"

        # Missing card_id for grade
        r3 = await flashcards(action="grade", rating="good")
        assert r3["ok"] is False
        assert r3["error_code"] == "invalid_input"

        # Invalid UUID for grade
        r4 = await flashcards(action="grade", card_id="not-a-uuid", rating="good")
        assert r4["ok"] is False
        assert r4["error_code"] == "invalid_input"

        # Invalid rating for grade
        r5 = await flashcards(action="grade", card_id=str(uuid.uuid4()), rating="invalid-rating")
        assert r5["ok"] is False
        assert r5["error_code"] == "invalid_input"

        # Invalid action
        r6 = await flashcards(action="unknown_action")
        assert r6["ok"] is False
        assert r6["error_code"] == "invalid_input"
    finally:
        reset_current_principal(token)
        set_flashcard_service(None)
        await engine.dispose()
