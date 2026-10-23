"""Service coordinating language conversation sessions and grammar translations (T11.2)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sahayak.core.db.session import UnitOfWork
from sahayak.core.errors import InvalidInputError, NotFoundError
from sahayak.core.events import publish as publish_event
from sahayak.modules.language.adapters.evaluator import LLMLanguagePracticeEvaluator
from sahayak.modules.language.adapters.practice import SQLAlchemyPracticeSessionRepository
from sahayak.modules.language.domain.languages import normalize_language, normalize_level
from sahayak.modules.language.domain.practice import (
    DEFAULT_MAX_TURNS,
    MAX_SESSION_TURNS_LIMIT,
    format_reply_turn_spoken,
    format_session_completed_spoken,
    format_start_conversation_spoken,
    format_translate_explain_spoken,
    get_scenario_starter,
    normalize_scenario,
)
from sahayak.modules.language.models import PracticeSession
from sahayak.modules.language.schemas import (
    CorrectionData,
    LanguagePracticeResponseData,
    PracticeSessionData,
    TranslateExplainData,
)
from sahayak.shared.llm.ports import LLMClient


class LanguagePracticeService:
    """Coordinates turn-limited conversation role-play and translate-explain workflows."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        llm_client: LLMClient | None = None,
        evaluator: LLMLanguagePracticeEvaluator | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._evaluator = evaluator or LLMLanguagePracticeEvaluator(llm_client=llm_client)
        self._clock = clock or (lambda: datetime.now(UTC))

    def _to_session_data(self, session: PracticeSession) -> PracticeSessionData:
        return PracticeSessionData(
            id=str(session.id),
            language=session.language,
            scenario=session.scenario,
            level=session.level,
            turns_completed=session.turns_completed,
            max_turns=session.max_turns,
            status=session.status,
            expires_at=session.expires_at.isoformat(),
        )

    async def start_conversation(
        self,
        user_id: uuid.UUID,
        language: str | None = None,
        scenario: str | None = None,
        level: str | None = None,
        max_turns: int | None = None,
    ) -> tuple[str, LanguagePracticeResponseData]:
        """Start a new turn-limited conversation practice session."""
        lang = normalize_language(language)
        scen = normalize_scenario(scenario)
        lvl = normalize_level(level)
        now = self._clock()

        turns_cap = max(1, min(MAX_SESSION_TURNS_LIMIT, max_turns or DEFAULT_MAX_TURNS))
        partner_greeting, greeting_meaning = get_scenario_starter(lang, scen)

        expires_at = now + timedelta(minutes=30)
        initial_history = [
            {
                "role": "assistant",
                "content": partner_greeting,
                "meaning": greeting_meaning,
            }
        ]

        async with UnitOfWork(self._session_factory) as uow:
            repo = SQLAlchemyPracticeSessionRepository(uow.session)

            # Close previous active session if any
            existing_active = await repo.get_active_session(user_id=user_id, language=lang)
            if existing_active:
                existing_active.status = "abandoned"
                await repo.save_session(existing_active)

            new_session = PracticeSession(
                user_id=user_id,
                language=lang,
                scenario=scen,
                level=lvl,
                turns_completed=0,
                max_turns=turns_cap,
                status="active",
                history=initial_history,
                expires_at=expires_at,
                created_at=now,
                updated_at=now,
            )
            created = await repo.create_session(new_session)

            spoken = format_start_conversation_spoken(
                language=lang,
                scenario=scen,
                partner_greeting=partner_greeting,
                english_meaning=greeting_meaning,
            )
            data = LanguagePracticeResponseData(
                action="start_conversation",
                language=lang,
                session=self._to_session_data(created),
                partner_response=partner_greeting,
                partner_response_english=greeting_meaning,
                turns_remaining=turns_cap,
            )
            return spoken, data

    async def reply(
        self,
        user_id: uuid.UUID,
        session_id_str: str | None,
        user_message: str | None,
    ) -> tuple[str, LanguagePracticeResponseData]:
        """Process user spoken reply, generate partner turn, and provide grammar tips."""
        if not user_message or not user_message.strip():
            raise InvalidInputError("Please provide your reply in the target language.")

        clean_user_message = user_message.strip()
        now = self._clock()

        async with UnitOfWork(self._session_factory) as uow:
            repo = SQLAlchemyPracticeSessionRepository(uow.session)

            session: PracticeSession | None = None
            if session_id_str:
                try:
                    s_id = uuid.UUID(session_id_str)
                except ValueError as exc:
                    raise InvalidInputError(f"Invalid session_id '{session_id_str}'.") from exc
                session = await repo.get_session_by_id(session_id=s_id, user_id=user_id)
            else:
                session = await repo.get_active_session(user_id=user_id)

            if not session:
                raise NotFoundError(
                    spoken=(
                        "I could not find an active conversation session. "
                        "Say start conversation to begin."
                    ),
                    detail=f"No active practice session found for user {user_id}",
                )

            # Check expiration
            if session.expires_at <= now:
                session.status = "expired"
                await repo.save_session(session)
                raise InvalidInputError(
                    spoken=(
                        "This conversation has expired. "
                        "Say start conversation to begin a new session."
                    ),
                    detail="Practice session has expired past TTL",
                )

            # Check status
            if session.status != "active":
                raise InvalidInputError(
                    spoken=(
                        "This conversation has already finished. "
                        "Say start conversation to begin a new session."
                    ),
                    detail=f"Practice session is {session.status}",
                )

            # Generate partner turn and feedback via evaluator
            eval_res = await self._evaluator.generate_turn(
                language=session.language,
                scenario=session.scenario,
                level=session.level,
                history=session.history,
                user_message=clean_user_message,
            )

            # Increment turns
            session.turns_completed += 1
            turns_left = max(0, session.max_turns - session.turns_completed)

            # Update history
            new_history = list(session.history)
            new_history.append({"role": "user", "content": clean_user_message})
            assistant_turn: dict[str, Any] = {
                "role": "assistant",
                "content": eval_res.partner_response,
                "meaning": eval_res.partner_response_english,
            }
            if eval_res.correction:
                assistant_turn["correction"] = eval_res.correction
                assistant_turn["explanation"] = eval_res.explanation
            new_history.append(assistant_turn)
            session.history = new_history
            session.updated_at = now

            is_concluded = turns_left == 0
            if is_concluded:
                session.status = "completed"

            await repo.save_session(session)

            # Emit transactional event
            publish_event(
                session=uow.session,
                aggregate="practice_session",
                type="language.practice.turn_completed",
                payload={
                    "user_id": str(user_id),
                    "session_id": str(session.id),
                    "language": session.language,
                    "turn": session.turns_completed,
                    "max_turns": session.max_turns,
                    "is_completed": is_concluded,
                },
            )

            correction_obj: CorrectionData | None = None
            if eval_res.correction:
                correction_obj = CorrectionData(
                    corrected_sentence=eval_res.correction,
                    explanation=eval_res.explanation or "Check grammar and agreement.",
                )

            spoken = format_reply_turn_spoken(
                partner_reply=eval_res.partner_response,
                english_meaning=eval_res.partner_response_english,
                turns_left=turns_left,
                correction=eval_res.correction,
                explanation=eval_res.explanation,
            )
            if is_concluded:
                concl = format_session_completed_spoken(
                    language=session.language,
                    scenario=session.scenario,
                    turns_completed=session.turns_completed,
                )
                spoken = f"{spoken} {concl}"[:300]

            data = LanguagePracticeResponseData(
                action="reply",
                language=session.language,
                session=self._to_session_data(session),
                partner_response=eval_res.partner_response,
                partner_response_english=eval_res.partner_response_english,
                correction=correction_obj,
                turns_remaining=turns_left,
            )
            return spoken, data

    async def translate_explain(
        self,
        user_id: uuid.UUID,
        query: str | None,
        target_language: str | None = None,
    ) -> tuple[str, LanguagePracticeResponseData]:
        """Translate phrase into target language and explain grammar."""
        if not query or not query.strip():
            raise InvalidInputError("Please specify the text or sentence to translate.")

        clean_query = query.strip()
        lang = normalize_language(target_language)

        res = await self._evaluator.translate_and_explain(
            query=clean_query,
            target_language=lang,
        )

        spoken = format_translate_explain_spoken(
            original=clean_query,
            translation=res.translation,
            grammar_note=res.grammar_note,
            example_sentence=res.example_sentence,
        )
        data = LanguagePracticeResponseData(
            action="translate_explain",
            language=lang,
            translate_explain=TranslateExplainData(
                original=clean_query,
                translation=res.translation,
                pronunciation_hint=res.pronunciation_hint,
                grammar_note=res.grammar_note,
                example_sentence=res.example_sentence,
            ),
        )
        return spoken, data

    async def end_session(
        self,
        user_id: uuid.UUID,
        session_id_str: str | None = None,
    ) -> tuple[str, LanguagePracticeResponseData]:
        """Explicitly conclude an active conversation practice session."""
        async with UnitOfWork(self._session_factory) as uow:
            repo = SQLAlchemyPracticeSessionRepository(uow.session)

            session: PracticeSession | None = None
            if session_id_str:
                try:
                    s_id = uuid.UUID(session_id_str)
                except ValueError as exc:
                    raise InvalidInputError(f"Invalid session_id '{session_id_str}'.") from exc
                session = await repo.get_session_by_id(session_id=s_id, user_id=user_id)
            else:
                session = await repo.get_active_session(user_id=user_id)

            if not session:
                raise NotFoundError(
                    spoken="No active conversation session was found to end.",
                    detail=f"No active session for user {user_id}",
                )

            session.status = "completed"
            await repo.save_session(session)

            spoken = format_session_completed_spoken(
                language=session.language,
                scenario=session.scenario,
                turns_completed=session.turns_completed,
            )
            data = LanguagePracticeResponseData(
                action="end",
                language=session.language,
                session=self._to_session_data(session),
                turns_remaining=0,
            )
            return spoken, data
