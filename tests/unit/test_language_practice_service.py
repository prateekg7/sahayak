"""Unit tests for LanguagePracticeService and LLMLanguagePracticeEvaluator (T11.2)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.config import get_settings
from sahayak.core.db.session import UnitOfWork
from sahayak.core.errors import InvalidInputError, NotFoundError
from sahayak.modules.language.adapters.evaluator import (
    LLMConversationTurnOutput,
    LLMLanguagePracticeEvaluator,
    LLMTranslateOutput,
)
from sahayak.modules.language.service.practice import LanguagePracticeService
from sahayak.shared.llm.fake import FakeLLMClient
from sahayak.shared.users.models import User


@pytest.mark.asyncio
async def test_language_practice_conversation_lifecycle() -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    current_time = datetime(2026, 10, 24, 12, 0, 0, tzinfo=UTC)

    def clock() -> datetime:
        return current_time

    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    try:
        async with UnitOfWork(session_factory) as uow:
            uow.session.add(User(id=user_a))
            uow.session.add(User(id=user_b))
            await uow.session.commit()

        service = LanguagePracticeService(
            session_factory=session_factory,
            clock=clock,
        )

        # 1. Start conversation in Spanish (cafe scenario, max 3 turns)
        spoken_start, data_start = await service.start_conversation(
            user_id=user_a,
            language="spanish",
            scenario="ordering_coffee",
            level="beginner",
            max_turns=3,
        )
        assert "Starting ordering food practice in Spanish" in spoken_start
        assert data_start.session is not None
        session_id = data_start.session.id
        assert data_start.turns_remaining == 3
        assert data_start.session.status == "active"
        assert len(spoken_start) <= 300

        # 2. Turn 1: User replies
        spoken_turn1, data_turn1 = await service.reply(
            user_id=user_a,
            session_id_str=session_id,
            user_message="Yo quiero un cafe con leche por favor.",
        )
        assert data_turn1.session is not None
        assert data_turn1.session.turns_completed == 1
        assert data_turn1.turns_remaining == 2
        assert data_turn1.session.status == "active"
        assert len(spoken_turn1) <= 300

        # 3. Turn 2: User replies with turn limit tracking
        spoken_turn2, data_turn2 = await service.reply(
            user_id=user_a,
            session_id_str=session_id,
            user_message="Quiero cafe y una tostada.",
        )
        assert data_turn2.session is not None
        assert data_turn2.session.turns_completed == 2
        assert data_turn2.turns_remaining == 1
        assert data_turn2.session.status == "active"

        # 4. Turn 3: Final turn completes the conversation session
        spoken_turn3, data_turn3 = await service.reply(
            user_id=user_a,
            session_id_str=session_id,
            user_message="Muchas gracias, la cuenta por favor.",
        )
        assert data_turn3.session is not None
        assert data_turn3.session.turns_completed == 3
        assert data_turn3.turns_remaining == 0
        assert data_turn3.session.status == "completed"
        assert "Great practice! You completed" in spoken_turn3

        # 5. Further replies fail because session is completed
        with pytest.raises(InvalidInputError, match="already finished"):
            await service.reply(
                user_id=user_a,
                session_id_str=session_id,
                user_message="Hola otra vez",
            )

        # 6. Cross-user isolation: User B cannot reply to User A's session
        with pytest.raises(NotFoundError):
            await service.reply(
                user_id=user_b,
                session_id_str=session_id,
                user_message="Intento entrar",
            )

    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_language_practice_expiration_and_abandonment() -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    current_time = datetime(2026, 10, 24, 14, 0, 0, tzinfo=UTC)

    def clock() -> datetime:
        return current_time

    user_id = uuid.uuid4()

    try:
        async with UnitOfWork(session_factory) as uow:
            uow.session.add(User(id=user_id))
            await uow.session.commit()

        service = LanguagePracticeService(session_factory=session_factory, clock=clock)

        # 1. Start session 1
        _, data1 = await service.start_conversation(
            user_id=user_id,
            language="french",
            scenario="ordering_food",
        )
        assert data1.session is not None
        session_id_1 = data1.session.id

        # 2. Starting a new session marks previous active session as abandoned
        _, data2 = await service.start_conversation(
            user_id=user_id,
            language="french",
            scenario="airport",
        )
        assert data2.session is not None
        session_id_2 = data2.session.id
        assert session_id_1 != session_id_2

        # Replying to abandoned session fails
        with pytest.raises(InvalidInputError, match="already finished"):
            await service.reply(
                user_id=user_id,
                session_id_str=session_id_1,
                user_message="Bonjour",
            )

        # 3. Advance clock past 30-minute TTL
        current_time = current_time + timedelta(minutes=35)

        # Replying to expired session fails with expired voice message
        with pytest.raises(InvalidInputError, match="expired"):
            await service.reply(
                user_id=user_id,
                session_id_str=session_id_2,
                user_message="Je voudrais un billet",
            )

    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_language_practice_llm_evaluator_and_translate() -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    turn_payload = LLMConversationTurnOutput(
        partner_response="Aqui esta su cafe senor.",
        partner_response_english="Here is your coffee sir.",
        correction="Yo quiero un cafe grande.",
        explanation="Remember to use un instead of una for masculine nouns.",
    )
    translate_payload = LLMTranslateOutput(
        translation="Donde esta la estacion de tren?",
        pronunciation_hint="dohn-deh ehs-tah lah ehs-tah-syohn deh trehn",
        grammar_note="Uses estar for physical location.",
        example_sentence="Perdon, donde esta la estacion de tren mas cercana?",
    )

    fake_client = FakeLLMClient(
        canned_json=[
            turn_payload.model_dump(),
            translate_payload.model_dump(),
        ]
    )
    evaluator = LLMLanguagePracticeEvaluator(llm_client=fake_client)
    service = LanguagePracticeService(
        session_factory=session_factory,
        evaluator=evaluator,
    )

    user_id = uuid.uuid4()

    try:
        async with UnitOfWork(session_factory) as uow:
            uow.session.add(User(id=user_id))
            await uow.session.commit()

        # 1. Start conversation
        _, start_data = await service.start_conversation(
            user_id=user_id,
            language="spanish",
            scenario="ordering_coffee",
        )
        assert start_data.session is not None
        s_id = start_data.session.id

        # 2. Reply receives structured feedback with correction and grammar tip
        spoken_turn, data_turn = await service.reply(
            user_id=user_id,
            session_id_str=s_id,
            user_message="Yo quiero una cafe grande.",
        )
        assert data_turn.correction is not None
        assert data_turn.correction.corrected_sentence == "Yo quiero un cafe grande."
        assert "Remember to use un" in data_turn.correction.explanation
        assert "Quick tip: say Yo quiero un cafe grande" in spoken_turn
        assert "Note: Remember to use un" in spoken_turn
        assert len(spoken_turn) <= 300

        # 3. Translate and explain
        spoken_tr, data_tr = await service.translate_explain(
            user_id=user_id,
            query="Where is the train station?",
            target_language="spanish",
        )
        assert data_tr.translate_explain is not None
        assert "Donde esta la estacion de tren?" in data_tr.translate_explain.translation
        assert "Uses estar for physical location" in data_tr.translate_explain.grammar_note
        assert len(spoken_tr) <= 300

        # 4. Explicit end_session
        spoken_end, data_end = await service.end_session(
            user_id=user_id,
            session_id_str=s_id,
        )
        assert data_end.session is not None
        assert data_end.session.status == "completed"
        assert "Great practice! You completed" in spoken_end

    finally:
        await engine.dispose()
