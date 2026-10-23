"""The 'vocab' MCP tool for daily vocabulary and spaced repetition reviews (T11.1)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from pydantic import ValidationError

from sahayak.core.auth.principal import get_current_principal, requires
from sahayak.core.envelope import fail, ok
from sahayak.core.errors import AuthRequiredError, InvalidInputError, SahayakError
from sahayak.core.idempotency import idempotent
from sahayak.core.observability.instrumentation import instrument_tool
from sahayak.modules.language.schemas import VocabAction, VocabRequest
from sahayak.modules.language.service.vocab import VocabService

logger = logging.getLogger(__name__)

_vocab_service: VocabService | None = None


def set_vocab_service(service: VocabService) -> None:
    """Inject the active VocabService instance."""
    global _vocab_service
    _vocab_service = service


def get_vocab_service() -> VocabService:
    """Retrieve the injected VocabService instance."""
    if _vocab_service is None:
        raise RuntimeError("VocabService has not been initialized.")
    return _vocab_service


VOCAB_DESCRIPTION = (
    "Manages daily vocabulary learning and spaced repetition review quizzes. "
    "Use when the user says 'Give me my word of the day in Spanish', 'Review my vocabulary', "
    "'Grade my word good', or 'What are my language stats?'. "
    "Do not use for conversational practice or translations; use language_practice instead."
)


@requires()
@idempotent(tool_name="vocab")
@instrument_tool("vocab", "language")
async def vocab(
    action: str = "word_of_day",
    language: str | None = None,
    level: str | None = None,
    user_word_id: str | None = None,
    rating: str | None = None,
    word: str | None = None,
    translation: str | None = None,
    pronunciation_hint: str | None = None,
    example_sentence: str | None = None,
    example_translation: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Execute vocabulary learning operations: word_of_day, review, grade, stats, add_word."""
    principal = get_current_principal()
    if principal is None or principal.anonymous or principal.user_id is None:
        raise AuthRequiredError(
            spoken="Please link your account in the Alexa app to practice vocabulary.",
            detail="User principal is anonymous or unauthenticated",
        )

    try:
        req = VocabRequest(
            action=action,  # type: ignore[arg-type]
            language=language,
            level=level,
            user_word_id=user_word_id,
            rating=rating,
            word=word,
            translation=translation,
            pronunciation_hint=pronunciation_hint,
            example_sentence=example_sentence,
            example_translation=example_translation,
        )
    except ValidationError as err:
        msg = err.errors()[0]["msg"] if err.errors() else "Invalid vocabulary request parameters."
        raise InvalidInputError(
            spoken=f"Invalid vocabulary request. {msg}",
            detail=str(err),
        ) from err

    service = get_vocab_service()
    user_id = principal.user_id

    try:
        match req.action:
            case VocabAction.WORD_OF_DAY:
                spoken, data = await service.get_or_create_word_of_day(
                    user_id=user_id,
                    language=req.language,
                    level=req.level,
                )
                next_actions = [
                    f"vocab(action='review', language='{data.language}')",
                    f"vocab(action='stats', language='{data.language}')",
                ]
                return ok(
                    spoken_summary=spoken,
                    data=data.model_dump(),
                    next_actions=next_actions,
                    module="language",
                    version="0.1.0",
                )

            case VocabAction.REVIEW:
                spoken, data = await service.get_due_reviews(
                    user_id=user_id,
                    language=req.language,
                )
                next_actions = []
                if data.user_word:
                    next_actions.append(
                        f"vocab(action='grade', user_word_id='{data.user_word.id}', rating='good')"
                    )
                return ok(
                    spoken_summary=spoken,
                    data=data.model_dump(),
                    next_actions=next_actions,
                    module="language",
                    version="0.1.0",
                )

            case VocabAction.GRADE:
                if not req.user_word_id:
                    raise InvalidInputError("Please specify the user_word_id to grade.")
                if not req.rating:
                    raise InvalidInputError(
                        "Please specify your review rating: again, hard, good, or easy."
                    )
                try:
                    target_id = uuid.UUID(req.user_word_id)
                except ValueError as exc:
                    raise InvalidInputError(
                        f"Invalid user_word_id format '{req.user_word_id}'."
                    ) from exc

                spoken, data = await service.grade_review(
                    user_id=user_id,
                    user_word_id=target_id,
                    rating=req.rating,
                )
                next_actions = [
                    f"vocab(action='review', language='{data.language}')",
                    f"vocab(action='stats', language='{data.language}')",
                ]
                return ok(
                    spoken_summary=spoken,
                    data=data.model_dump(),
                    next_actions=next_actions,
                    module="language",
                    version="0.1.0",
                )

            case VocabAction.STATS:
                spoken, data = await service.get_stats(
                    user_id=user_id,
                    language=req.language,
                )
                next_actions = [
                    f"vocab(action='word_of_day', language='{data.language}')",
                    f"vocab(action='review', language='{data.language}')",
                ]
                return ok(
                    spoken_summary=spoken,
                    data=data.model_dump(),
                    next_actions=next_actions,
                    module="language",
                    version="0.1.0",
                )

            case VocabAction.ADD_WORD:
                if (
                    not req.word
                    or not req.translation
                    or not req.pronunciation_hint
                    or not req.example_sentence
                    or not req.example_translation
                ):
                    raise InvalidInputError(
                        "Adding a word requires: word, translation, pronunciation_hint, "
                        "example_sentence, and example_translation."
                    )
                spoken, data = await service.add_word(
                    user_id=user_id,
                    language=req.language,
                    level=req.level,
                    word=req.word,
                    translation=req.translation,
                    pronunciation_hint=req.pronunciation_hint,
                    example_sentence=req.example_sentence,
                    example_translation=req.example_translation,
                )
                return ok(
                    spoken_summary=spoken,
                    data=data.model_dump(),
                    next_actions=[f"vocab(action='review', language='{data.language}')"],
                    module="language",
                    version="0.1.0",
                )

            case _:
                raise InvalidInputError(
                    spoken=f"Unsupported vocabulary action {req.action}.",
                    detail=f"Unsupported action: {req.action}",
                )

    except SahayakError as err:
        return fail(err, module="language", version="0.1.0")
    except Exception as exc:
        logger.exception("Unexpected error in vocab tool: %s", exc)
        return fail(SahayakError(), module="language", version="0.1.0")
