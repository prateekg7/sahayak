"""Service layer coordinating vocabulary learning, reviews, and SM-2 spaced repetition (T11.1)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sahayak.core.db.session import UnitOfWork
from sahayak.core.errors import InvalidInputError, NotFoundError
from sahayak.core.events import publish as publish_event
from sahayak.modules.language.adapters.vocab import (
    SQLAlchemyUserWordRepository,
    SQLAlchemyWordRepository,
)
from sahayak.modules.language.domain.languages import normalize_language, normalize_level
from sahayak.modules.language.domain.seeds import get_seed_words_for
from sahayak.modules.language.domain.vocab import (
    format_graded_spoken,
    format_review_card_spoken,
    format_stats_spoken,
    format_word_of_day_spoken,
    validate_word_payload,
)
from sahayak.modules.language.models import UserWord, Word
from sahayak.modules.language.schemas import (
    UserWordData,
    VocabResponseData,
    WordData,
)
from sahayak.shared.srs.sm2 import calculate_sm2


class VocabService:
    """Coordinates vocabulary learning, daily words, reviews, and SM-2 repetition."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    def _to_word_data(self, word: Word) -> WordData:
        return WordData(
            id=str(word.id),
            language=word.language,
            level=word.level,
            word=word.word,
            translation=word.translation,
            pronunciation_hint=word.pronunciation_hint,
            example_sentence=word.example_sentence,
            example_translation=word.example_translation,
            part_of_speech=word.part_of_speech,
        )

    def _to_user_word_data(self, user_word: UserWord) -> UserWordData:
        return UserWordData(
            id=str(user_word.id),
            user_id=str(user_word.user_id),
            word_id=str(user_word.word_id),
            ease=user_word.ease,
            interval_days=user_word.interval_days,
            repetitions=user_word.repetitions,
            due_at=user_word.due_at.isoformat(),
            last_reviewed_at=(
                user_word.last_reviewed_at.isoformat() if user_word.last_reviewed_at else None
            ),
            word=self._to_word_data(user_word.word) if user_word.word else None,
        )

    async def get_or_create_word_of_day(
        self,
        user_id: uuid.UUID,
        language: str | None = None,
        level: str | None = None,
    ) -> tuple[str, VocabResponseData]:
        """Retrieve today's word of the day or assign the next unlearned word."""
        lang = normalize_language(language)
        lvl = normalize_level(level)
        now = self._clock()

        start_of_day = datetime(now.year, now.month, now.day, tzinfo=UTC)

        async with UnitOfWork(self._session_factory) as uow:
            word_repo = SQLAlchemyWordRepository(uow.session)
            user_word_repo = SQLAlchemyUserWordRepository(uow.session)

            # 1. Check if user already received a word of the day today in this language
            today_words = await user_word_repo.get_words_learned_today(
                user_id=user_id,
                language=lang,
                start_of_day=start_of_day,
            )
            if today_words:
                today_uw = today_words[0]
                spoken = format_word_of_day_spoken(
                    word=today_uw.word.word,
                    language=lang,
                    translation=today_uw.word.translation,
                    pronunciation_hint=today_uw.word.pronunciation_hint,
                    example_sentence=today_uw.word.example_sentence,
                    example_translation=today_uw.word.example_translation,
                    is_already_learned=True,
                )
                data = VocabResponseData(
                    action="word_of_day",
                    language=lang,
                    word=self._to_word_data(today_uw.word),
                    user_word=self._to_user_word_data(today_uw),
                )
                return spoken, data

            # 2. Find an unlearned word for the user
            unlearned = await word_repo.find_unlearned_words(
                user_id=user_id,
                language=lang,
                level=lvl,
                limit=5,
            )

            chosen_word: Word | None = None
            if unlearned:
                chosen_word = unlearned[0]
            else:
                # Seed words if cache is empty or all existing seeds were learned
                seeds = get_seed_words_for(lang, lvl)
                for s in seeds:
                    existing = await word_repo.get_word_by_text(lang, s.word)
                    if not existing:
                        new_w = Word(
                            language=s.language,
                            level=s.level,
                            word=s.word,
                            translation=s.translation,
                            pronunciation_hint=s.pronunciation_hint,
                            example_sentence=s.example_sentence,
                            example_translation=s.example_translation,
                            part_of_speech=s.part_of_speech,
                        )
                        await word_repo.create_word(new_w)

                # Re-query after seeding
                refreshed_unlearned = await word_repo.find_unlearned_words(
                    user_id=user_id,
                    language=lang,
                    level=lvl,
                    limit=5,
                )
                if refreshed_unlearned:
                    chosen_word = refreshed_unlearned[0]

            if not chosen_word:
                # Fallback if every single word in this level has been learned
                all_unlearned = await word_repo.find_unlearned_words(
                    user_id=user_id,
                    language=lang,
                    level=None,
                    limit=1,
                )
                if all_unlearned:
                    chosen_word = all_unlearned[0]
                else:
                    spoken = (
                        f"You have completed all available {lang.capitalize()} vocabulary words! "
                        "Great job. Review your mastered words or try another language."
                    )
                    data = VocabResponseData(
                        action="word_of_day",
                        language=lang,
                    )
                    return spoken, data

            # 3. Create UserWord scheduled for review tomorrow
            due_at = now + timedelta(days=1)
            new_user_word = UserWord(
                user_id=user_id,
                word_id=chosen_word.id,
                ease=2.5,
                interval_days=1,
                repetitions=0,
                due_at=due_at,
                created_at=now,
            )
            created_uw = await user_word_repo.create_user_word(new_user_word)
            created_uw.word = chosen_word

            spoken = format_word_of_day_spoken(
                word=chosen_word.word,
                language=lang,
                translation=chosen_word.translation,
                pronunciation_hint=chosen_word.pronunciation_hint,
                example_sentence=chosen_word.example_sentence,
                example_translation=chosen_word.example_translation,
                is_already_learned=False,
            )
            data = VocabResponseData(
                action="word_of_day",
                language=lang,
                word=self._to_word_data(chosen_word),
                user_word=self._to_user_word_data(created_uw),
            )
            return spoken, data

    async def get_due_reviews(
        self,
        user_id: uuid.UUID,
        language: str | None = None,
    ) -> tuple[str, VocabResponseData]:
        """Retrieve cards currently due for spaced repetition review."""
        lang = normalize_language(language)
        now = self._clock()

        async with UnitOfWork(self._session_factory) as uow:
            user_word_repo = SQLAlchemyUserWordRepository(uow.session)
            due_words = await user_word_repo.get_due_words(
                user_id=user_id,
                language=lang,
                now=now,
                limit=10,
            )

            if not due_words:
                spoken = (
                    f"You have no {lang.capitalize()} words due for review right now. "
                    "Great job staying caught up!"
                )
                data = VocabResponseData(
                    action="review",
                    language=lang,
                    next_due_words=[],
                )
                return spoken, data

            first_card = due_words[0]
            remaining_count = len(due_words) - 1
            spoken = format_review_card_spoken(
                word=first_card.word.word,
                language=lang,
                pronunciation_hint=first_card.word.pronunciation_hint,
                remaining_count=remaining_count,
            )
            data = VocabResponseData(
                action="review",
                language=lang,
                word=self._to_word_data(first_card.word),
                user_word=self._to_user_word_data(first_card),
                next_due_words=[self._to_user_word_data(uw) for uw in due_words],
            )
            return spoken, data

    async def grade_review(
        self,
        user_id: uuid.UUID,
        user_word_id: uuid.UUID,
        rating: str,
    ) -> tuple[str, VocabResponseData]:
        """Apply SuperMemo-2 rating to reschedule a user's word review."""
        now = self._clock()

        async with UnitOfWork(self._session_factory) as uow:
            user_word_repo = SQLAlchemyUserWordRepository(uow.session)
            user_word = await user_word_repo.get_user_word_by_id(
                user_word_id=user_word_id,
                user_id=user_id,
            )
            if not user_word:
                raise NotFoundError(
                    spoken="I could not find that vocabulary word to grade.",
                    detail=f"UserWord {user_word_id} not found for user {user_id}",
                )

            try:
                sm2_res = calculate_sm2(
                    rating=rating,
                    ease=user_word.ease,
                    interval_days=user_word.interval_days,
                    repetitions=user_word.repetitions,
                )
            except ValueError as exc:
                raise InvalidInputError(
                    f"Invalid rating '{rating}'. Expected one of: again, hard, good, easy."
                ) from exc

            user_word.ease = sm2_res.ease
            user_word.interval_days = sm2_res.interval_days
            user_word.repetitions = sm2_res.repetitions
            user_word.due_at = now + timedelta(days=sm2_res.interval_days)
            user_word.last_reviewed_at = now

            saved = await user_word_repo.save_user_word(user_word)

            # Publish transactional outbox event
            publish_event(
                session=uow.session,
                aggregate="vocab",
                type="language.vocab.graded",
                payload={
                    "user_id": str(user_id),
                    "user_word_id": str(user_word.id),
                    "word": user_word.word.word,
                    "rating": rating,
                    "interval_days": sm2_res.interval_days,
                    "ease": sm2_res.ease,
                },
            )

            spoken = format_graded_spoken(
                word=user_word.word.word,
                rating=rating.lower().strip(),
                interval_days=sm2_res.interval_days,
                translation=user_word.word.translation,
            )
            data = VocabResponseData(
                action="grade",
                language=user_word.word.language,
                word=self._to_word_data(user_word.word),
                user_word=self._to_user_word_data(saved),
            )
            return spoken, data

    async def get_stats(
        self,
        user_id: uuid.UUID,
        language: str | None = None,
    ) -> tuple[str, VocabResponseData]:
        """Retrieve vocabulary statistics for the user."""
        lang = normalize_language(language)
        now = self._clock()

        async with UnitOfWork(self._session_factory) as uow:
            user_word_repo = SQLAlchemyUserWordRepository(uow.session)
            stats = await user_word_repo.get_stats(
                user_id=user_id,
                language=lang,
                now=now,
            )

            spoken = format_stats_spoken(
                language=lang,
                total_learned=stats["total_learned"],
                due_count=stats["due_count"],
                mastered_count=stats["mastered_count"],
            )
            data = VocabResponseData(
                action="stats",
                language=lang,
                stats=stats,
            )
            return spoken, data

    async def add_word(
        self,
        user_id: uuid.UUID,
        language: str | None,
        level: str | None,
        word: str,
        translation: str,
        pronunciation_hint: str,
        example_sentence: str,
        example_translation: str,
    ) -> tuple[str, VocabResponseData]:
        """Manually add and start learning a custom vocabulary word."""
        validate_word_payload(word, translation, pronunciation_hint)
        lang = normalize_language(language)
        lvl = normalize_level(level)
        now = self._clock()

        async with UnitOfWork(self._session_factory) as uow:
            word_repo = SQLAlchemyWordRepository(uow.session)
            user_word_repo = SQLAlchemyUserWordRepository(uow.session)

            existing_word = await word_repo.get_word_by_text(lang, word)
            if not existing_word:
                word_entity = Word(
                    language=lang,
                    level=lvl,
                    word=word.strip(),
                    translation=translation.strip(),
                    pronunciation_hint=pronunciation_hint.strip(),
                    example_sentence=example_sentence.strip(),
                    example_translation=example_translation.strip(),
                )
                persisted_word = await word_repo.create_word(word_entity)
            else:
                persisted_word = existing_word

            # Check if user already has it
            existing_user_word = await user_word_repo.get_user_word(user_id, persisted_word.id)
            if existing_user_word:
                spoken = (
                    f"You are already learning {word} in {lang.capitalize()}. "
                    f"It means {persisted_word.translation}."
                )
                data = VocabResponseData(
                    action="add_word",
                    language=lang,
                    word=self._to_word_data(persisted_word),
                    user_word=self._to_user_word_data(existing_user_word),
                )
                return spoken, data

            new_uw = UserWord(
                user_id=user_id,
                word_id=persisted_word.id,
                ease=2.5,
                interval_days=1,
                repetitions=0,
                due_at=now + timedelta(days=1),
                created_at=now,
            )
            created_uw = await user_word_repo.create_user_word(new_uw)
            created_uw.word = persisted_word

            spoken = (
                f"Added {word} to your {lang.capitalize()} vocabulary, meaning {translation}. "
                "First review scheduled for tomorrow."
            )
            data = VocabResponseData(
                action="add_word",
                language=lang,
                word=self._to_word_data(persisted_word),
                user_word=self._to_user_word_data(created_uw),
            )
            return spoken, data
