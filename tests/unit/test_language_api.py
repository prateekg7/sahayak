"""Unit tests for LanguageAPI cross-module interactions (T11.1)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.config import get_settings
from sahayak.core.db.session import UnitOfWork
from sahayak.modules.language.api import LanguageAPI
from sahayak.modules.language.service.vocab import VocabService
from sahayak.shared.users.models import User


@pytest.mark.asyncio
async def test_language_api_due_vocab_count() -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    user_id = uuid.uuid4()
    now = datetime(2026, 10, 24, 12, 0, 0, tzinfo=UTC)

    vocab_svc = VocabService(session_factory=session_factory, clock=lambda: now)
    api = LanguageAPI(session_factory=session_factory, clock=lambda: now)

    try:
        async with UnitOfWork(session_factory) as uow:
            uow.session.add(User(id=user_id))
            await uow.session.commit()

        # Initially 0 due
        count_0 = await api.get_due_vocab_count(user_id, "spanish")
        assert count_0 == 0

        # Learn a word
        await vocab_svc.get_or_create_word_of_day(user_id, "spanish")

        # Before due time: still 0 due
        count_before = await api.get_due_vocab_count(user_id, "spanish")
        assert count_before == 0

    finally:
        await engine.dispose()
