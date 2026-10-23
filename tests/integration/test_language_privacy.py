"""Integration test for language module GDPR export and erasure hooks (T11.1)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.config import get_settings
from sahayak.core.db.session import UnitOfWork
from sahayak.core.module import Deps
from sahayak.modules.language.module import module as language_module
from sahayak.modules.language.service.vocab import VocabService
from sahayak.shared.users.models import User


@pytest.mark.asyncio
async def test_language_privacy_export_and_erasure() -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    deps = Deps(session_factory=session_factory)
    language_module.register_tools(None, deps=deps)
    vocab_svc = VocabService(session_factory=session_factory)

    try:
        async with UnitOfWork(session_factory) as uow:
            uow.session.add_all([User(id=user_a), User(id=user_b)])
            await uow.session.commit()

        # User A learns words
        await vocab_svc.get_or_create_word_of_day(
            user_id=user_a,
            language="spanish",
            level="beginner",
        )
        await vocab_svc.add_word(
            user_id=user_a,
            language="spanish",
            level="beginner",
            word="ventana",
            translation="window",
            pronunciation_hint="vehn-tah-nah",
            example_sentence="Abre la ventana por favor.",
            example_translation="Open the window please.",
        )

        # 1. GDPR Export for User A
        export_data = await language_module.export_user_data(str(user_a))
        assert "user_words" in export_data
        assert len(export_data["user_words"]) >= 2
        exported_words = [uw["word"]["word"] for uw in export_data["user_words"]]
        assert "ventana" in exported_words

        # 2. GDPR Erasure for User A
        await language_module.delete_user_data(str(user_a))

        # 3. Verify User A data is purged
        post_erase_export = await language_module.export_user_data(str(user_a))
        assert len(post_erase_export["user_words"]) == 0

    finally:
        await engine.dispose()
