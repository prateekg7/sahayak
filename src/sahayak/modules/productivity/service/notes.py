"""Note service orchestrating voice note saving, full-text search, and speech chunking (T5.3)."""

from __future__ import annotations

import uuid
from typing import Any

from sahayak.core.db.session import UnitOfWork
from sahayak.core.errors import InvalidInputError, NotFoundError
from sahayak.modules.productivity.adapters.notes import SQLAlchemyNoteRepository
from sahayak.modules.productivity.domain.notes import (
    chunk_note_for_speech,
    clean_note_text,
    format_search_results_spoken,
)
from sahayak.modules.productivity.schemas import NoteData, NotesResponseData


class NoteService:
    """Service managing voice notes and full-text searches with transaction isolation."""

    def __init__(self, session_factory: Any) -> None:
        self.session_factory = session_factory

    def _parse_id(self, raw_id: str | None) -> uuid.UUID:
        if not raw_id:
            raise InvalidInputError("note_id is required for this action")
        try:
            return uuid.UUID(raw_id)
        except (ValueError, TypeError) as err:
            raise InvalidInputError(f"Invalid note_id '{raw_id}'") from err

    async def add_note(
        self,
        user_id: uuid.UUID,
        content: str | None,
        tags: list[str] | None = None,
    ) -> tuple[str, NotesResponseData, list[str]]:
        if not content:
            raise InvalidInputError("Note content cannot be empty")

        clean = clean_note_text(content)

        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyNoteRepository(uow.session)
            note = await repo.create_note(user_id=user_id, content=clean, tags=tags)
            note_dict = note.to_dict()

        spoken = "Saved your note. Say search notes or read latest note anytime."
        data = NotesResponseData(
            action="add",
            note=NoteData(**note_dict),
            count=1,
        )
        next_actions = ["read latest note", "search notes"]
        return spoken, data, next_actions

    async def search_notes(
        self,
        user_id: uuid.UUID,
        query: str | None,
        limit: int = 5,
    ) -> tuple[str, NotesResponseData, list[str]]:
        if not query or not query.strip():
            raise InvalidInputError("Search query cannot be empty")

        clean_query = query.strip()

        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyNoteRepository(uow.session)
            notes = await repo.search_notes(user_id=user_id, query=clean_query, limit=limit)
            notes_dicts = [n.to_dict() for n in notes]

        spoken = format_search_results_spoken(clean_query, notes_dicts)
        data = NotesResponseData(
            action="search",
            notes=[NoteData(**d) for d in notes_dicts],
            count=len(notes_dicts),
        )
        next_actions = ["read latest note"] if notes_dicts else ["add a note"]
        return spoken, data, next_actions

    async def read_latest_note(
        self,
        user_id: uuid.UUID,
    ) -> tuple[str, NotesResponseData, list[str]]:
        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyNoteRepository(uow.session)
            note = await repo.get_latest_note(user_id)
            if note is None:
                raise NotFoundError("You do not have any saved notes yet.")
            note_dict = note.to_dict()

        spoken_chunk, has_more = chunk_note_for_speech(note.content)
        data = NotesResponseData(
            action="read_latest",
            note=NoteData(**note_dict),
            count=1,
            has_more=has_more,
        )
        next_actions = ["read more"] if has_more else ["add a note", "search notes"]
        return spoken_chunk, data, next_actions

    async def delete_note(
        self,
        user_id: uuid.UUID,
        note_id_str: str | None,
    ) -> tuple[str, NotesResponseData, list[str]]:
        note_id = self._parse_id(note_id_str)

        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemyNoteRepository(uow.session)
            deleted = await repo.delete_note(user_id=user_id, note_id=note_id)
            if not deleted:
                raise NotFoundError(f"Note '{note_id}' not found")

        spoken = "Deleted the note."
        data = NotesResponseData(
            action="delete",
            count=1,
        )
        next_actions = ["add a note"]
        return spoken, data, next_actions
