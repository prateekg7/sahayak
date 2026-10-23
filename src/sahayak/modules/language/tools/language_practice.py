"""The 'language_practice' MCP tool for conversational turns and translations (T11.2)."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from sahayak.core.auth.principal import get_current_principal, requires
from sahayak.core.envelope import fail, ok
from sahayak.core.errors import AuthRequiredError, InvalidInputError, SahayakError
from sahayak.core.idempotency import idempotent
from sahayak.core.observability.instrumentation import instrument_tool
from sahayak.modules.language.schemas import (
    LanguagePracticeAction,
    LanguagePracticeRequest,
)
from sahayak.modules.language.service.practice import LanguagePracticeService

logger = logging.getLogger(__name__)

_practice_service: LanguagePracticeService | None = None


def set_language_practice_service(service: LanguagePracticeService) -> None:
    """Inject the active LanguagePracticeService instance."""
    global _practice_service
    _practice_service = service


def get_language_practice_service() -> LanguagePracticeService:
    """Retrieve the injected LanguagePracticeService instance."""
    if _practice_service is None:
        raise RuntimeError("LanguagePracticeService has not been initialized.")
    return _practice_service


LANGUAGE_PRACTICE_DESCRIPTION = (
    "Practice short conversational role-play sessions and get grammar-aware translations. "
    "Use when the user says 'Let us practice Spanish', 'Reply to conversation', "
    "'Translate how much is this to Spanish', or 'End conversation'. "
    "Do not use for spaced repetition flashcards or daily word; use vocab instead."
)


@requires()
@idempotent(tool_name="language_practice")
@instrument_tool("language_practice", "language")
async def language_practice(
    action: str = "start_conversation",
    session_id: str | None = None,
    language: str | None = None,
    scenario: str | None = None,
    level: str | None = None,
    user_message: str | None = None,
    query: str | None = None,
    target_language: str | None = None,
    max_turns: int | None = 5,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Execute conversational practice: start_conversation, reply, translate_explain, end."""
    principal = get_current_principal()
    if principal is None or principal.anonymous or principal.user_id is None:
        raise AuthRequiredError(
            spoken="Please link your account in the Alexa app to practice language conversations.",
            detail="User principal is anonymous or unauthenticated",
        )

    try:
        req = LanguagePracticeRequest(
            action=action,  # type: ignore[arg-type]
            session_id=session_id,
            language=language,
            scenario=scenario,
            level=level,
            user_message=user_message,
            query=query,
            target_language=target_language,
            max_turns=max_turns,
        )
    except ValidationError as err:
        msg = (
            err.errors()[0]["msg"]
            if err.errors()
            else "Invalid language practice request parameters."
        )
        raise InvalidInputError(
            spoken=f"Invalid language practice request. {msg}",
            detail=str(err),
        ) from err

    service = get_language_practice_service()
    user_id = principal.user_id

    try:
        match req.action:
            case LanguagePracticeAction.START_CONVERSATION:
                spoken, data = await service.start_conversation(
                    user_id=user_id,
                    language=req.language,
                    scenario=req.scenario,
                    level=req.level,
                    max_turns=req.max_turns,
                )
                session_id_val = data.session.id if data.session else ""
                next_actions = [
                    f"language_practice(action='reply', session_id='{session_id_val}', "
                    "user_message='...')",
                    f"language_practice(action='end', session_id='{session_id_val}')",
                ]
                return ok(
                    spoken_summary=spoken,
                    data=data.model_dump(),
                    next_actions=next_actions,
                    module="language",
                    version="0.1.0",
                )

            case LanguagePracticeAction.REPLY:
                spoken, data = await service.reply(
                    user_id=user_id,
                    session_id_str=req.session_id,
                    user_message=req.user_message,
                )
                session_id_val = data.session.id if data.session else ""
                next_actions = []
                if data.turns_remaining and data.turns_remaining > 0:
                    next_actions.append(
                        f"language_practice(action='reply', session_id='{session_id_val}', "
                        "user_message='...')"
                    )
                next_actions.append(
                    f"language_practice(action='start_conversation', language='{data.language}')"
                )
                return ok(
                    spoken_summary=spoken,
                    data=data.model_dump(),
                    next_actions=next_actions,
                    module="language",
                    version="0.1.0",
                )

            case LanguagePracticeAction.TRANSLATE_EXPLAIN:
                target_lang = req.target_language or req.language
                spoken, data = await service.translate_explain(
                    user_id=user_id,
                    query=req.query,
                    target_language=target_lang,
                )
                next_actions = [
                    f"language_practice(action='start_conversation', language='{data.language}')",
                    f"vocab(action='word_of_day', language='{data.language}')",
                ]
                return ok(
                    spoken_summary=spoken,
                    data=data.model_dump(),
                    next_actions=next_actions,
                    module="language",
                    version="0.1.0",
                )

            case LanguagePracticeAction.END:
                spoken, data = await service.end_session(
                    user_id=user_id,
                    session_id_str=req.session_id,
                )
                next_actions = [
                    f"language_practice(action='start_conversation', language='{data.language}')",
                    f"vocab(action='stats', language='{data.language}')",
                ]
                return ok(
                    spoken_summary=spoken,
                    data=data.model_dump(),
                    next_actions=next_actions,
                    module="language",
                    version="0.1.0",
                )

            case _:
                raise InvalidInputError(
                    spoken=f"Unsupported language practice action {req.action}.",
                    detail=f"Unsupported action: {req.action}",
                )

    except SahayakError as err:
        return fail(err, module="language", version="0.1.0")
    except Exception as exc:
        logger.exception("Unexpected error in language_practice tool: %s", exc)
        return fail(SahayakError(), module="language", version="0.1.0")
