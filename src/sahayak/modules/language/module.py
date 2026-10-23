"""Language module conforming to the Module protocol (T11.1, T11.2)."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from sahayak.core.db.session import UnitOfWork
from sahayak.core.module import Deps, HealthStatus
from sahayak.modules.language.models import PracticeSession, UserWord


class LanguageModule:
    """Language learning module for vocabulary acquisition and practice."""

    def __init__(self) -> None:
        self._deps: Deps | None = None
        self._api: Any = None

    @property
    def name(self) -> str:
        return "language"

    @property
    def version(self) -> str:
        return "0.1.0"

    @property
    def api(self) -> Any:
        if self._api is None:
            if self._deps is None or self._deps.session_factory is None:
                return None
            from sahayak.modules.language.api import LanguageAPI

            self._api = LanguageAPI(
                session_factory=self._deps.session_factory,  # type: ignore[arg-type]
            )
        return self._api

    def register_tools(self, mcp: Any, deps: Deps) -> None:
        """Register MCP tools for language learning module."""
        self._deps = deps
        if deps.session_factory is not None:
            from sahayak.modules.language.service.practice import LanguagePracticeService
            from sahayak.modules.language.service.vocab import VocabService
            from sahayak.modules.language.tools.language_practice import (
                set_language_practice_service,
            )
            from sahayak.modules.language.tools.vocab import set_vocab_service

            vocab_service = VocabService(
                session_factory=deps.session_factory,  # type: ignore[arg-type]
            )
            set_vocab_service(vocab_service)

            practice_service = LanguagePracticeService(
                session_factory=deps.session_factory,  # type: ignore[arg-type]
                llm_client=deps.llm_client,
            )
            set_language_practice_service(practice_service)

        from sahayak.modules.language.tools.language_practice import (
            LANGUAGE_PRACTICE_DESCRIPTION,
            language_practice,
        )
        from sahayak.modules.language.tools.vocab import (
            VOCAB_DESCRIPTION,
            vocab,
        )

        tool_decorator = getattr(mcp, "tool", None)
        if callable(tool_decorator):
            tool_decorator(name="vocab", description=VOCAB_DESCRIPTION)(vocab)
            tool_decorator(name="language_practice", description=LANGUAGE_PRACTICE_DESCRIPTION)(
                language_practice
            )
        elif hasattr(mcp, "add_tool"):
            mcp.add_tool(vocab, name="vocab", description=VOCAB_DESCRIPTION)
            mcp.add_tool(
                language_practice,
                name="language_practice",
                description=LANGUAGE_PRACTICE_DESCRIPTION,
            )

    def register_jobs(self, worker: Any) -> None:
        """Register background worker jobs for language module."""
        pass

    def migrations_path(self) -> str | None:
        return str(Path(__file__).parent / "migrations")

    def health(self) -> HealthStatus:
        if self._deps is not None and self._deps.session_factory is None:
            return HealthStatus(healthy=False, detail="PostgreSQL session factory missing")
        return HealthStatus(healthy=True, detail="Language module is operational")

    def on_event(self, event: Any) -> None:
        """Dispatched domain events hook."""
        pass

    async def export_user_data(self, user_id: str) -> dict[str, Any]:
        """GDPR Right to Access: export user vocabulary and practice sessions."""
        if self._deps is None or self._deps.session_factory is None:
            return {}

        uid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
        async with UnitOfWork(self._deps.session_factory) as uow:
            res_uw = await uow.session.execute(
                select(UserWord)
                .options(selectinload(UserWord.word))
                .where(UserWord.user_id == uid)
                .order_by(UserWord.created_at.asc())
            )
            user_words = res_uw.scalars().all()

            res_ps = await uow.session.execute(
                select(PracticeSession)
                .where(PracticeSession.user_id == uid)
                .order_by(PracticeSession.created_at.asc())
            )
            sessions = res_ps.scalars().all()

            return {
                "user_words": [uw.to_dict() for uw in user_words],
                "practice_sessions": [s.to_dict() for s in sessions],
            }

    async def delete_user_data(self, user_id: str) -> None:
        """GDPR Right to Erasure: delete all vocabulary and practice records for user."""
        if self._deps is None or self._deps.session_factory is None:
            return

        uid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
        async with UnitOfWork(self._deps.session_factory) as uow:
            await uow.session.execute(delete(UserWord).where(UserWord.user_id == uid))
            await uow.session.execute(delete(PracticeSession).where(PracticeSession.user_id == uid))


module = LanguageModule()
