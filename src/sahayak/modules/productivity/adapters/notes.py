"""SQLAlchemy implementation of NoteRepositoryPort with full-text and partial search (T5.3)."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from sahayak.modules.productivity.models import Note


class SQLAlchemyNoteRepository:
    """Repository managing voice notes with full-text and partial text search."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_note(
        self,
        user_id: uuid.UUID,
        content: str,
        tags: list[str] | None = None,
    ) -> Note:
        """Persist a new note."""
        note = Note(
            user_id=user_id,
            content=content.strip(),
            tags=tags or [],
        )
        self.session.add(note)
        await self.session.flush()
        return note

    async def get_note(self, user_id: uuid.UUID, note_id: uuid.UUID) -> Note | None:
        """Retrieve note by ID, scoped by user_id."""
        stmt = select(Note).where(Note.id == note_id, Note.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_latest_note(self, user_id: uuid.UUID) -> Note | None:
        """Retrieve most recently recorded note for user."""
        stmt = select(Note).where(Note.user_id == user_id).order_by(Note.created_at.desc()).limit(1)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def search_notes(
        self,
        user_id: uuid.UUID,
        query: str,
        limit: int = 5,
    ) -> list[Note]:
        """Search notes using Postgres full-text and partial substring match."""
        clean = query.strip()
        if not clean:
            return []

        # Full-text tsquery condition
        fts_match = func.to_tsvector("english", Note.content).op("@@")(
            func.plainto_tsquery("english", clean)
        )
        # Partial substring match condition
        ilike_match = Note.content.ilike(f"%{clean}%")

        stmt = (
            select(Note)
            .where(Note.user_id == user_id, or_(fts_match, ilike_match))
            .order_by(Note.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete_note(self, user_id: uuid.UUID, note_id: uuid.UUID) -> bool:
        """Delete note by ID, scoped by user_id."""
        stmt = delete(Note).where(Note.id == note_id, Note.user_id == user_id).returning(Note.id)
        result = await self.session.execute(stmt)
        deleted = result.scalars().first()
        return deleted is not None
