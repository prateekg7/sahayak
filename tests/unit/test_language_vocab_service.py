"""Unit tests for VocabService spaced repetition and word of the day (T11.1)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.config import get_settings
from sahayak.core.db.session import UnitOfWork
from sahayak.core.errors import InvalidInputError, NotFoundError
from sahayak.modules.language.service.vocab import VocabService
from sahayak.shared.users.models import User


@pytest.mark.asyncio
async def test_vocab_service_lifecycle_and_sm2_reviews() -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    current_time = datetime(2026, 10, 24, 10, 0, 0, tzinfo=UTC)

    def clock() -> datetime:
        return current_time

    service = VocabService(session_factory=session_factory, clock=clock)
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    try:
        async with UnitOfWork(session_factory) as uow:
            uow.session.add(User(id=user_a))
            uow.session.add(User(id=user_b))
            await uow.session.commit()

        # 1. User A requests word of the day
        spoken_1, data_1 = await service.get_or_create_word_of_day(
            user_id=user_a,
            language="spanish",
            level="beginner",
        )
        assert data_1.word is not None
        assert data_1.user_word is not None
        word_1 = data_1.word.word
        uw_id_1 = uuid.UUID(data_1.user_word.id)
        assert "Your word of the day in Spanish is" in spoken_1

        # 2. Calling word_of_day on the same day returns the same word without duplicate creation
        spoken_2, data_2 = await service.get_or_create_word_of_day(
            user_id=user_a,
            language="spanish",
            level="beginner",
        )
        assert data_2.word is not None
        assert data_2.word.word == word_1
        assert "Your word today in Spanish is" in spoken_2

        # 3. Initially, no cards are due (card 1 was scheduled for tomorrow)
        spoken_rev_0, data_rev_0 = await service.get_due_reviews(
            user_id=user_a,
            language="spanish",
        )
        assert "no Spanish words due for review right now" in spoken_rev_0
        assert len(data_rev_0.next_due_words) == 0

        # 4. Advance clock by 1 day and 1 hour: card 1 is now due!
        current_time = current_time + timedelta(days=1, hours=1)

        # 4a. Next day's word of the day assigns a DIFFERENT word
        spoken_next_day, data_next_day = await service.get_or_create_word_of_day(
            user_id=user_a,
            language="spanish",
            level="beginner",
        )
        assert data_next_day.word is not None
        word_2 = data_next_day.word.word
        assert word_2 != word_1, "User should receive a different word on subsequent days"

        # 5. Check due reviews
        spoken_rev_1, data_rev_1 = await service.get_due_reviews(
            user_id=user_a,
            language="spanish",
        )
        assert data_rev_1.user_word is not None
        assert data_rev_1.user_word.id == str(uw_id_1)
        assert "How do you translate" in spoken_rev_1

        # 6. User B cannot grade User A's word
        with pytest.raises(NotFoundError, match="could not find that vocabulary word"):
            await service.grade_review(
                user_id=user_b,
                user_word_id=uw_id_1,
                rating="good",
            )

        # 7. Invalid rating is rejected
        with pytest.raises(InvalidInputError, match="Invalid rating"):
            await service.grade_review(
                user_id=user_a,
                user_word_id=uw_id_1,
                rating="invalid_rating",
            )

        # 8. User A grades card 1 with "good"
        spoken_grade, data_grade = await service.grade_review(
            user_id=user_a,
            user_word_id=uw_id_1,
            rating="good",
        )
        assert data_grade.user_word is not None
        assert data_grade.user_word.repetitions == 1
        assert data_grade.user_word.interval_days == 1
        assert "Marked" in spoken_grade
        assert "good" in spoken_grade

        # 9. Grade again on next cycle with "good" -> interval increases to 6 days
        current_time = current_time + timedelta(days=1)
        spoken_grade_2, data_grade_2 = await service.grade_review(
            user_id=user_a,
            user_word_id=uw_id_1,
            rating="good",
        )
        assert data_grade_2.user_word is not None
        assert data_grade_2.user_word.repetitions == 2
        assert data_grade_2.user_word.interval_days == 6
        assert "in 6 days" in spoken_grade_2

        # 10. Check stats
        spoken_stats, data_stats = await service.get_stats(
            user_id=user_a,
            language="spanish",
        )
        assert data_stats.stats["total_learned"] == 2
        assert "you have learned 2 words" in spoken_stats

        # 11. Add custom word
        spoken_add, data_add = await service.add_word(
            user_id=user_a,
            language="spanish",
            level="beginner",
            word="gato",
            translation="cat",
            pronunciation_hint="gah-toh",
            example_sentence="El gato duerme en el sofa.",
            example_translation="The cat sleeps on the sofa.",
        )
        assert data_add.word is not None
        assert data_add.word.word == "gato"
        assert "Added gato to your Spanish vocabulary" in spoken_add

    finally:
        await engine.dispose()
