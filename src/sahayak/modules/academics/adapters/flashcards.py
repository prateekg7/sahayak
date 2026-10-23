"""SQLAlchemy repository implementation for flashcards and decks."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from sahayak.modules.academics.models import Card, Deck
from sahayak.modules.academics.ports import FlashcardPort


class SQLAlchemyFlashcardRepository(FlashcardPort):
    """PostgreSQL adapter managing decks and SM-2 flashcard persistence."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create_deck(self, user_id: uuid.UUID, name: str) -> Deck:
        """Find an existing deck by user and name, or create a new one."""
        clean_name = name.strip() or "General"
        stmt = select(Deck).where(Deck.user_id == user_id, Deck.name == clean_name)
        res = await self._session.execute(stmt)
        deck = res.scalar_one_or_none()
        if deck is not None:
            return deck

        deck = Deck(user_id=user_id, name=clean_name)
        self._session.add(deck)
        try:
            await self._session.flush()
            return deck
        except IntegrityError:
            # Concurrent creation race condition
            res_reload = await self._session.execute(stmt)
            return res_reload.scalar_one()

    async def find_deck(self, user_id: uuid.UUID, name: str) -> Deck | None:
        """Find a deck by user and name if it exists."""
        clean_name = name.strip()
        stmt = select(Deck).where(Deck.user_id == user_id, Deck.name == clean_name)
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def create_card(
        self,
        user_id: uuid.UUID,
        deck_id: uuid.UUID,
        front: str,
        back: str,
        due_at: datetime | None = None,
    ) -> Card:
        """Create and persist a new card in the given deck."""
        kwargs: dict[str, Any] = {
            "user_id": user_id,
            "deck_id": deck_id,
            "front": front.strip(),
            "back": back.strip(),
        }
        if due_at is not None:
            kwargs["due_at"] = due_at
        card = Card(**kwargs)
        self._session.add(card)
        await self._session.flush()
        return card

    async def get_card(self, card_id: uuid.UUID, user_id: uuid.UUID) -> Card | None:
        """Retrieve a card ensuring user ownership."""
        stmt = select(Card).where(Card.id == card_id, Card.user_id == user_id)
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_next_due_card(
        self,
        user_id: uuid.UUID,
        deck_id: uuid.UUID | None = None,
        before: datetime | None = None,
    ) -> Card | None:
        """Fetch the single next due card for review ordered by due_at ASC."""
        stmt = select(Card).where(Card.user_id == user_id)
        if deck_id is not None:
            stmt = stmt.where(Card.deck_id == deck_id)
        if before is not None:
            stmt = stmt.where(Card.due_at <= before)
        stmt = stmt.order_by(Card.due_at.asc()).limit(1)
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_due_cards(
        self,
        user_id: uuid.UUID,
        deck_id: uuid.UUID | None = None,
        before: datetime | None = None,
        limit: int = 5,
    ) -> Sequence[Card]:
        """Fetch due cards for review ordered by due_at ASC up to limit."""
        stmt = select(Card).where(Card.user_id == user_id)
        if deck_id is not None:
            stmt = stmt.where(Card.deck_id == deck_id)
        if before is not None:
            stmt = stmt.where(Card.due_at <= before)
        stmt = stmt.order_by(Card.due_at.asc()).limit(limit)
        res = await self._session.execute(stmt)
        return list(res.scalars().all())

    async def count_due_cards(
        self,
        user_id: uuid.UUID,
        deck_id: uuid.UUID | None = None,
        before: datetime | None = None,
    ) -> int:
        """Count total due cards for a user on or before the given timestamp."""
        stmt = select(func.count(Card.id)).where(Card.user_id == user_id)
        if deck_id is not None:
            stmt = stmt.where(Card.deck_id == deck_id)
        if before is not None:
            stmt = stmt.where(Card.due_at <= before)
        res = await self._session.execute(stmt)
        return int(res.scalar_one() or 0)

    async def save_card(self, card: Card) -> Card:
        """Persist updates to an existing card."""
        self._session.add(card)
        await self._session.flush()
        return card
