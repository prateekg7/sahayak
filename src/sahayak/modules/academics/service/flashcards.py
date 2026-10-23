"""Service layer for flashcard creation, review scheduling, and SM-2 grading."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sahayak.core.db.session import SessionFactory, UnitOfWork
from sahayak.core.errors import InvalidInputError, NotFoundError
from sahayak.core.events import publish as publish_event
from sahayak.modules.academics.adapters.flashcards import SQLAlchemyFlashcardRepository
from sahayak.modules.academics.models import Card
from sahayak.shared.srs.sm2 import ReviewRating, calculate_sm2

MAX_CONTENT_LENGTH = 2000


@dataclass(frozen=True)
class DueCardsInfo:
    """Summary of cards currently due for spaced repetition review."""

    total_due: int
    cards: list[Card]


class FlashcardService:
    """Domain service orchestrating decks and spaced repetition flashcard reviews."""

    def __init__(
        self,
        session_factory: SessionFactory,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    async def add_card(
        self,
        user_id: uuid.UUID,
        front: str,
        back: str,
        deck_name: str | None = None,
    ) -> Card:
        """Create and persist a new flashcard in the specified or default deck."""
        clean_front = front.strip()
        clean_back = back.strip()

        if not clean_front:
            raise InvalidInputError(
                spoken="Please provide text for the front of the flashcard.",
                detail="Flashcard front cannot be empty",
            )
        if not clean_back:
            raise InvalidInputError(
                spoken="Please provide text for the back of the flashcard.",
                detail="Flashcard back cannot be empty",
            )
        if len(clean_front) > MAX_CONTENT_LENGTH or len(clean_back) > MAX_CONTENT_LENGTH:
            raise InvalidInputError(
                spoken="The flashcard content is too long. Please keep it under 2000 characters.",
                detail=f"Content exceeds {MAX_CONTENT_LENGTH} characters",
            )

        now = self._clock()
        async with UnitOfWork(self._session_factory) as uow:
            repo = SQLAlchemyFlashcardRepository(uow.session)
            deck = await repo.get_or_create_deck(user_id, deck_name or "General")
            card = await repo.create_card(
                user_id=user_id,
                deck_id=deck.id,
                front=clean_front,
                back=clean_back,
                due_at=now,
            )
            return card

    async def get_next_due(
        self,
        user_id: uuid.UUID,
        deck_name: str | None = None,
    ) -> Card | None:
        """Fetch the single next due flashcard for review."""
        now = self._clock()
        async with UnitOfWork(self._session_factory) as uow:
            repo = SQLAlchemyFlashcardRepository(uow.session)
            deck_id: uuid.UUID | None = None
            if deck_name:
                deck = await repo.find_deck(user_id, deck_name)
                if deck is None:
                    return None
                deck_id = deck.id

            return await repo.get_next_due_card(
                user_id=user_id,
                deck_id=deck_id,
                before=now,
            )

    async def grade_card(
        self,
        user_id: uuid.UUID,
        card_id: uuid.UUID,
        rating: str,
    ) -> Card:
        """Evaluate a card review, update SM-2 scheduling parameters, and record progress."""
        try:
            rating_enum = ReviewRating(rating.lower().strip())
        except ValueError as exc:
            raise InvalidInputError(
                spoken="Please grade the card as again, hard, good, or easy.",
                detail=f"Invalid review rating: {rating}",
            ) from exc

        now = self._clock()
        async with UnitOfWork(self._session_factory) as uow:
            repo = SQLAlchemyFlashcardRepository(uow.session)
            card = await repo.get_card(card_id, user_id)
            if card is None:
                raise NotFoundError(
                    spoken="I couldn't find that flashcard to grade.",
                    detail=f"Card {card_id} not found for user {user_id}",
                )

            sm2_res = calculate_sm2(
                rating=rating_enum,
                ease=card.ease,
                interval_days=card.interval_days,
                repetitions=card.repetitions,
            )

            card.ease = sm2_res.ease
            card.interval_days = sm2_res.interval_days
            card.repetitions = sm2_res.repetitions
            card.due_at = now + timedelta(days=sm2_res.interval_days)

            updated = await repo.save_card(card)

            # Emit transactional domain event
            publish_event(
                session=uow.session,
                aggregate="flashcard",
                type="academics.flashcard.graded",
                payload={
                    "user_id": str(user_id),
                    "card_id": str(card_id),
                    "deck_id": str(card.deck_id),
                    "rating": rating_enum.value,
                    "interval_days": sm2_res.interval_days,
                    "repetitions": sm2_res.repetitions,
                    "ease": sm2_res.ease,
                },
            )
            return updated

    async def list_due(
        self,
        user_id: uuid.UUID,
        deck_name: str | None = None,
        limit: int = 5,
    ) -> DueCardsInfo:
        """Return total count and next batch of cards currently due for review."""
        now = self._clock()
        clamped_limit = max(1, min(20, limit))

        async with UnitOfWork(self._session_factory) as uow:
            repo = SQLAlchemyFlashcardRepository(uow.session)
            deck_id: uuid.UUID | None = None
            if deck_name:
                deck = await repo.find_deck(user_id, deck_name)
                if deck is None:
                    return DueCardsInfo(total_due=0, cards=[])
                deck_id = deck.id

            total = await repo.count_due_cards(user_id, deck_id=deck_id, before=now)
            due_list = list(
                await repo.list_due_cards(
                    user_id=user_id,
                    deck_id=deck_id,
                    before=now,
                    limit=clamped_limit,
                )
            )
            return DueCardsInfo(total_due=total, cards=due_list)
