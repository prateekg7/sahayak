"""The 'notes' MCP tool for voice notes and full-text search (T5.3)."""

from __future__ import annotations

import logging
from typing import Any

from sahayak.core.auth.principal import get_current_principal, requires
from sahayak.core.envelope import fail, ok
from sahayak.core.errors import AuthRequiredError, InvalidInputError, SahayakError
from sahayak.core.idempotency import idempotent
from sahayak.core.observability.instrumentation import instrument_tool
from sahayak.modules.productivity.schemas import NoteAction, NotesRequest
from sahayak.modules.productivity.service.notes import NoteService

logger = logging.getLogger(__name__)

_note_service: NoteService | None = None


def set_note_service(service: NoteService) -> None:
    """Inject the active NoteService instance."""
    global _note_service
    _note_service = service


def get_note_service() -> NoteService:
    """Retrieve the injected NoteService instance."""
    if _note_service is None:
        raise RuntimeError("NoteService has not been initialized.")
    return _note_service


NOTES_DESCRIPTION = (
    "Capture quick voice notes, search past notes by keyword, and read back your thoughts. "
    "Use when the user says 'Take a note: meeting ideas', 'Search my notes for recipe', "
    "or 'Read my latest note'. "
    "Do not use for to-do items or deadlines; use the tasks tool instead."
)


@requires()
@idempotent(tool_name="notes")
@instrument_tool("notes", "productivity")
async def notes(
    action: str,
    content: str | None = None,
    query: str | None = None,
    note_id: str | None = None,
    tags: list[str] | None = None,
    limit: int = 5,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Execute voice note operations (add, search, read_latest, delete)."""
    principal = get_current_principal()
    if principal is None or principal.anonymous or principal.user_id is None:
        raise AuthRequiredError(
            spoken="Please link your account in the Alexa app to manage personal voice notes.",
            detail="Account linking required for notes tool",
        )

    try:
        req = NotesRequest(
            action=NoteAction(action.strip().lower()),
            content=content,
            query=query,
            note_id=note_id,
            tags=tags or [],
            limit=limit,
            request_id=request_id,
        )

        service = get_note_service()

        if req.action == NoteAction.ADD:
            spoken, data, next_actions = await service.add_note(
                user_id=principal.user_id,
                content=req.content,
                tags=req.tags,
            )
        elif req.action == NoteAction.SEARCH:
            spoken, data, next_actions = await service.search_notes(
                user_id=principal.user_id,
                query=req.query,
                limit=req.limit,
            )
        elif req.action == NoteAction.READ_LATEST:
            spoken, data, next_actions = await service.read_latest_note(
                user_id=principal.user_id,
            )
        elif req.action == NoteAction.DELETE:
            spoken, data, next_actions = await service.delete_note(
                user_id=principal.user_id,
                note_id_str=req.note_id,
            )
        else:
            raise InvalidInputError(
                spoken=f"Unsupported action {req.action}.",
                detail=f"Unsupported note action '{req.action}'",
            )

        return ok(
            spoken_summary=spoken,
            data=data.model_dump(),
            next_actions=next_actions,
            module="productivity",
            version="0.1.0",
        )
    except SahayakError as err:
        return fail(err, module="productivity", version="0.1.0")
    except Exception as exc:
        logger.exception("Unexpected error in notes tool: %s", exc)
        return fail(SahayakError(), module="productivity", version="0.1.0")
