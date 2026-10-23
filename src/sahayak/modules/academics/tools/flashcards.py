"""Flashcards MCP tool for spaced repetition study and review management."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sahayak.core.auth.principal import get_current_principal, requires
from sahayak.core.config import get_settings
from sahayak.core.envelope import fail, ok
from sahayak.core.errors import InvalidInputError, SahayakError
from sahayak.core.idempotency import idempotent
from sahayak.core.observability.instrumentation import instrument_tool
from sahayak.modules.academics.schemas import (
    FlashcardCardData,
    FlashcardsRequest,
    FlashcardsResponseData,
)
from sahayak.modules.academics.service.flashcards import FlashcardService

logger = logging.getLogger(__name__)

FLASHCARDS_DESCRIPTION = (
    "Manages flashcards and spaced repetition study reviews. "
    "Use when the user wants to create, review, grade, or list study flashcards, such as "
    "'Alexa, add a flashcard: capital of Australia is Canberra' or 'Alexa, review my flashcards'. "
    "Do not use for taking multiple-choice quizzes; use quiz_start or quiz_answer instead."
)

_flashcard_service: FlashcardService | None = None


def set_flashcard_service(service: FlashcardService | None) -> None:
    """Set or override the module-level flashcard service instance."""
    global _flashcard_service
    _flashcard_service = service


def get_flashcard_service() -> FlashcardService:
    """Return the configured flashcard service instance or lazily initialize one."""
    global _flashcard_service
    if _flashcard_service is None:
        settings = get_settings()
        from sahayak.core.db.session import create_engine, create_session_factory

        engine = create_engine(settings)
        session_factory = create_session_factory(engine)
        _flashcard_service = FlashcardService(session_factory=session_factory)
    return _flashcard_service


@requires()
@idempotent(tool_name="flashcards")
async def flashcards(
    action: str,
    front: str | None = None,
    back: str | None = None,
    deck: str | None = None,
    card_id: str | None = None,
    rating: str | None = None,
    limit: int = 5,
    request_id: str = "",
) -> dict[str, Any]:
    """Create, review, grade, and list flashcards with spaced repetition scheduling."""
    if request_id:
        from sahayak.core.request_id import set_request_id

        set_request_id(request_id)

    async with instrument_tool("flashcards", "academics"):
        service = get_flashcard_service()
        principal = get_current_principal()
        user_id = principal.user_id
        if user_id is None:
            # Enforced by @requires decorator, but for typing safety
            from sahayak.core.errors import AuthRequiredError

            return fail(AuthRequiredError(), module="academics", version="0.1.0")

        try:
            req = FlashcardsRequest(
                action=action,  # type: ignore[arg-type]
                front=front,
                back=back,
                deck=deck,
                card_id=card_id,
                rating=rating,  # type: ignore[arg-type]
                limit=limit,
                request_id=request_id or None,
            )
        except Exception as val_err:
            return fail(
                InvalidInputError(
                    spoken=(
                        "Please provide a valid action like add, review next, grade, or list due."
                    ),
                    detail=str(val_err),
                ),
                module="academics",
                version="0.1.0",
            )

        try:
            if req.action == "add":
                if not req.front or not req.front.strip():
                    raise InvalidInputError(
                        spoken="Please provide the front text for the flashcard.",
                        detail="Missing front text for flashcard",
                    )
                if not req.back or not req.back.strip():
                    raise InvalidInputError(
                        spoken="Please provide the back text for the flashcard.",
                        detail="Missing back text for flashcard",
                    )

                deck_name = req.deck or "General"
                card = await service.add_card(
                    user_id=user_id,
                    front=req.front,
                    back=req.back,
                    deck_name=deck_name,
                )
                spoken = f"Added flashcard to {deck_name}: {card.front}."
                data = FlashcardsResponseData(
                    action="add",
                    card=FlashcardCardData(
                        card_id=str(card.id),
                        front=card.front,
                        back=card.back,
                        deck=deck_name,
                        due_at=card.due_at.isoformat(),
                    ),
                ).model_dump()
                return ok(
                    spoken_summary=spoken,
                    data=data,
                    next_actions=["Say 'review flashcards' to start reviewing."],
                    module="academics",
                    version="0.1.0",
                )

            elif req.action == "review_next":
                due_card = await service.get_next_due(user_id=user_id, deck_name=req.deck)
                if due_card is not None:
                    spoken = f"Card: {due_card.front}. Say 'show answer' or grade it."
                    data = FlashcardsResponseData(
                        action="review_next",
                        card=FlashcardCardData(
                            card_id=str(due_card.id),
                            front=due_card.front,
                            back=due_card.back,
                            due_at=due_card.due_at.isoformat(),
                        ),
                        total_due=1,
                    ).model_dump()
                    next_actions = ["Say 'show answer' or grade again, hard, good, or easy."]
                else:
                    spoken = "You are all caught up! No flashcards are due for review right now."
                    data = FlashcardsResponseData(
                        action="review_next",
                        card=None,
                        total_due=0,
                    ).model_dump()
                    next_actions = ["Say 'add a flashcard' to create a new card."]

                return ok(
                    spoken_summary=spoken,
                    data=data,
                    next_actions=next_actions,
                    module="academics",
                    version="0.1.0",
                )

            elif req.action == "grade":
                if not req.card_id or not req.card_id.strip():
                    raise InvalidInputError(
                        spoken="Please specify which flashcard you are grading.",
                        detail="Missing card_id for action 'grade'",
                    )
                if not req.rating:
                    raise InvalidInputError(
                        spoken="Please provide a rating such as again, hard, good, or easy.",
                        detail="Missing rating for action 'grade'",
                    )

                try:
                    target_card_id = uuid.UUID(req.card_id.strip())
                except (ValueError, TypeError) as exc:
                    raise InvalidInputError(
                        spoken="Please provide a valid card identifier.",
                        detail=f"Invalid UUID for card_id: {req.card_id}",
                    ) from exc

                graded_card = await service.grade_card(
                    user_id=user_id,
                    card_id=target_card_id,
                    rating=req.rating,
                )

                days = graded_card.interval_days
                days_text = "in 1 day" if days == 1 else f"in {days} days"
                spoken = f"Card graded as {req.rating}. Next review {days_text}."
                data = FlashcardsResponseData(
                    action="grade",
                    card=FlashcardCardData(
                        card_id=str(graded_card.id),
                        front=graded_card.front,
                        back=graded_card.back,
                        ease=graded_card.ease,
                        interval_days=graded_card.interval_days,
                        repetitions=graded_card.repetitions,
                        due_at=graded_card.due_at.isoformat(),
                    ),
                    rating=req.rating,
                    next_review_days=days,
                ).model_dump()
                return ok(
                    spoken_summary=spoken,
                    data=data,
                    next_actions=["Say 'review next' to review the next flashcard."],
                    module="academics",
                    version="0.1.0",
                )

            elif req.action == "list_due":
                info = await service.list_due(
                    user_id=user_id,
                    deck_name=req.deck,
                    limit=req.limit,
                )
                if info.total_due == 0:
                    spoken = "You have no flashcards due for review right now."
                elif info.total_due == 1:
                    spoken = "You have 1 flashcard due for review."
                else:
                    spoken = f"You have {info.total_due} flashcards due for review."

                cards_data = [
                    FlashcardCardData(
                        card_id=str(c.id),
                        front=c.front,
                        due_at=c.due_at.isoformat(),
                    )
                    for c in info.cards
                ]
                data = FlashcardsResponseData(
                    action="list_due",
                    total_due=info.total_due,
                    cards=cards_data,
                ).model_dump()
                return ok(
                    spoken_summary=spoken,
                    data=data,
                    next_actions=["Say 'review flashcards' to begin."],
                    module="academics",
                    version="0.1.0",
                )

            else:
                raise InvalidInputError(
                    spoken=(
                        f"Unknown action {req.action}. "
                        "Please choose add, review next, grade, or list due."
                    ),
                    detail=f"Invalid action: {req.action}",
                )

        except SahayakError as err:
            return fail(err, module="academics", version="0.1.0")
        except Exception as exc:
            logger.exception("Unexpected error in flashcards tool: %s", exc)
            return fail(SahayakError(), module="academics", version="0.1.0")
