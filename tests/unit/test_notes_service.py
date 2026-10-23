"""Unit tests for NoteService orchestration, persistence, full-text search, and deletion (T5.3)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.config import get_settings
from sahayak.core.db.session import UnitOfWork
from sahayak.core.errors import InvalidInputError, NotFoundError
from sahayak.modules.productivity.service.notes import NoteService
from sahayak.shared.users.models import User


@pytest.mark.asyncio
async def test_note_lifecycle_add_search_read_delete() -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    user_id = uuid.uuid4()
    service = NoteService(session_factory=session_factory)

    try:
        # Seed user
        async with UnitOfWork(session_factory) as uow:
            uow.session.add(User(id=user_id))
            await uow.session.flush()

        # 1. Add note
        spoken_add, data_add, next_add = await service.add_note(
            user_id=user_id,
            content="Pick up organic vegetables and whole grain bread tomorrow morning",
            tags=["groceries", "errands"],
        )
        assert "Saved your note" in spoken_add
        assert data_add.note is not None
        note_id = data_add.note.id
        assert data_add.note.tags == ["groceries", "errands"]

        # 2. Add second note
        await service.add_note(
            user_id=user_id,
            content="Project roadmap architecture meeting scheduled for 3pm",
            tags=["work"],
        )

        # 3. Read latest note
        spoken_read, data_read, _ = await service.read_latest_note(user_id=user_id)
        assert data_read.note is not None
        assert "Project roadmap" in data_read.note.content
        assert "Project roadmap architecture meeting" in spoken_read

        # 4. Search notes
        spoken_search, data_search, _ = await service.search_notes(
            user_id=user_id,
            query="vegetables",
        )
        assert "Found 1 note for vegetables" in spoken_search
        assert data_search.count == 1
        assert "organic vegetables" in data_search.notes[0].content

        # 5. Delete the first note
        spoken_del, data_del, _ = await service.delete_note(
            user_id=user_id,
            note_id_str=note_id,
        )
        assert "Deleted the note" in spoken_del
        assert data_del.count == 1

        # Search again for vegetables -> not found
        spoken_none, data_none, _ = await service.search_notes(
            user_id=user_id,
            query="vegetables",
        )
        assert "could not find any notes" in spoken_none
        assert data_none.count == 0

    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_note_service_errors() -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    user_id = uuid.uuid4()
    service = NoteService(session_factory=session_factory)

    try:
        # Empty add raises InvalidInputError
        with pytest.raises(InvalidInputError):
            await service.add_note(user_id=user_id, content="")

        # Empty search raises InvalidInputError
        with pytest.raises(InvalidInputError):
            await service.search_notes(user_id=user_id, query="   ")

        # Read latest when empty raises NotFoundError
        with pytest.raises(NotFoundError):
            await service.read_latest_note(user_id=user_id)

        # Delete invalid uuid raises InvalidInputError
        with pytest.raises(InvalidInputError):
            await service.delete_note(user_id=user_id, note_id_str="not-a-uuid")

        # Delete non-existent note raises NotFoundError
        with pytest.raises(NotFoundError):
            await service.delete_note(user_id=user_id, note_id_str=str(uuid.uuid4()))

    finally:
        await engine.dispose()
