"""End-to-end contract scenarios replaying all PRD §2.1 voice dialogs (T3.15).

Replays each dialog from PRD §2.1 over Streamable HTTP MCP transport:
1. Quiz:
   - "Alexa, ask Sahayak to quiz me on photosynthesis." -> quiz_start
   - "Option B." -> quiz_answer
   - Completion -> event handled -> "How am I doing?" -> progress_report
   - "Quiz me on my weak topics." -> quiz_start(source="weak_topics")
2. Flashcards:
   - "Add a flashcard: capital of Australia is Canberra." -> flashcards(action="add")
   - "Review my flashcards." -> flashcards(action="review_next")
   - Grade "good" -> flashcards(action="grade")
3. Study plan:
   - "My chemistry exam is on the 15th. Make a study plan." -> study_plan(action="create")
   - "What should I study today?" -> study_plan(action="today")
4. Brief:
   - "Give me a quick brief on the French Revolution." -> topic_brief(topic=...)
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.auth.jwt import JWTValidator
from sahayak.core.config import get_settings
from sahayak.core.db.session import UnitOfWork
from sahayak.core.events import DomainEvent
from sahayak.core.module import Deps, ModuleRegistry
from sahayak.main import create_app
from sahayak.modules.academics.adapters.question_bank import SQLAlchemyQuestionBank
from sahayak.modules.academics.models import DifficultyLevel, Question
from sahayak.modules.academics.module import AcademicsModule
from sahayak.modules.academics.service.brief import TopicBriefService
from sahayak.modules.academics.service.flashcards import FlashcardService
from sahayak.modules.academics.service.plan import StudyPlanService
from sahayak.modules.academics.service.progress import ProgressService
from sahayak.modules.academics.service.quiz import QuizService
from sahayak.modules.academics.tools.brief import set_brief_service
from sahayak.modules.academics.tools.flashcards import set_flashcard_service
from sahayak.modules.academics.tools.progress import set_progress_service
from sahayak.modules.academics.tools.quiz import set_quiz_service
from sahayak.modules.academics.tools.study_plan import set_study_plan_service
from sahayak.shared.content.wikipedia import GroundingResult, WikipediaClient
from sahayak.shared.users.models import User, UserIdentity


class E2EMockWikipediaClient(WikipediaClient):
    """Deterministic Wikipedia grounding for French Revolution brief."""

    async def get_grounding(
        self,
        topic: str,
        *,
        language: str = "en",
        max_chars: int = 2000,
        timeout: float = 5.0,
    ) -> GroundingResult | None:
        return GroundingResult(
            title="French Revolution",
            raw_extract=(
                "The French Revolution was a period of political and societal change in France "
                "that began in 1789 and ended in 1799. It established popular sovereignty, "
                "abolished feudalism, and reshaped modern European politics."
            ),
            sanitized_text=(
                "The French Revolution was a period of political and societal change in France "
                "that began in 1789 and ended in 1799. It established popular sovereignty, "
                "abolished feudalism, and reshaped modern European politics."
            ),
            wrapped_prompt_text=(
                "<grounded_source_data>The French Revolution...</grounded_source_data>"
            ),
            url="https://en.wikipedia.org/wiki/French_Revolution",
        )


@pytest.fixture(scope="module")
def e2e_rsa_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def make_test_token(key: rsa.RSAPrivateKey, *, sub: str) -> str:
    now = int(time.time())
    payload = {
        "sub": sub,
        "iss": "https://auth.example.com",
        "aud": "sahayak-api",
        "exp": now + 3600,
        "iat": now,
        "nbf": now,
        "scope": "academics.read academics.write",
    }
    return jwt.encode(payload, key, algorithm="RS256", headers={"kid": "sec-test-key"})


def assert_voice_summary_valid(spoken_summary: str) -> None:
    """Check voice UX rules on spoken summary: <= 300 chars, no markdown."""
    assert spoken_summary, "spoken_summary must not be empty"
    assert len(spoken_summary) <= 300, (
        f"spoken_summary exceeds 300 chars: length={len(spoken_summary)}: {spoken_summary!r}"
    )
    assert "**" not in spoken_summary, "spoken_summary must not contain bold markdown"
    assert "##" not in spoken_summary, "spoken_summary must not contain heading markdown"
    assert "`" not in spoken_summary, "spoken_summary must not contain code tick markdown"


@pytest.mark.asyncio
async def test_academics_prd_dialogs_e2e_contract_suite(
    e2e_rsa_key: rsa.RSAPrivateKey,
) -> None:
    """Full HTTP contract scenario executing all PRD §2.1 voice dialogs."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    # 1. Setup user identity
    user_id = uuid.uuid4()
    user_sub = f"student_{uuid.uuid4().hex[:8]}"

    async with UnitOfWork(session_factory) as uow:
        uow.session.add(User(id=user_id))
        uow.session.add(
            UserIdentity(
                id=uuid.uuid4(),
                user_id=user_id,
                issuer="https://auth.example.com",
                subject=user_sub,
            )
        )

        # 2. Seed Photosynthesis question bank
        bank = SQLAlchemyQuestionBank(uow.session)
        topic_photo = await bank.get_or_create_topic("photosynthesis", "Photosynthesis")
        questions = [
            Question(
                topic_id=topic_photo.id,
                difficulty=DifficultyLevel.MEDIUM,
                stem="In photosynthesis, what gas is consumed by plant cells?",
                options={
                    "A": "Oxygen",
                    "B": "Carbon dioxide",
                    "C": "Nitrogen",
                    "D": "Hydrogen",
                },
                correct_key="B",
                explanation="Carbon dioxide is fixed in the Calvin cycle.",
                content_hash=f"photo_{uuid.uuid4().hex[:8]}",
                prompt_version="v1",
                model="test-model",
            ),
            Question(
                topic_id=topic_photo.id,
                difficulty=DifficultyLevel.MEDIUM,
                stem="What pigment absorbs light energy in chloroplasts?",
                options={
                    "A": "Hemoglobin",
                    "B": "Chlorophyll",
                    "C": "Carotene",
                    "D": "Melanin",
                },
                correct_key="B",
                explanation="Chlorophyll absorbs red and blue wavelengths.",
                content_hash=f"photo_{uuid.uuid4().hex[:8]}",
                prompt_version="v1",
                model="test-model",
            ),
            Question(
                topic_id=topic_photo.id,
                difficulty=DifficultyLevel.MEDIUM,
                stem="What sugar is the primary product of photosynthesis?",
                options={
                    "A": "Glucose",
                    "B": "Lactose",
                    "C": "Sucrose",
                    "D": "Fructose",
                },
                correct_key="A",
                explanation="Glucose provides energy and structural cellulose.",
                content_hash=f"photo_{uuid.uuid4().hex[:8]}",
                prompt_version="v1",
                model="test-model",
            ),
        ]
        await bank.insert_questions(questions)

        # Seed Weak Topic questions
        topic_optics = await bank.get_or_create_topic("optics", "Optics")
        q_optics = Question(
            topic_id=topic_optics.id,
            difficulty=DifficultyLevel.MEDIUM,
            stem="What lens shape converges parallel light rays to a focal point?",
            options={
                "A": "Convex lens",
                "B": "Concave lens",
                "C": "Flat glass",
                "D": "Cylindrical",
            },
            correct_key="A",
            explanation="Convex lenses bend rays inward toward a focus.",
            content_hash=f"optics_{uuid.uuid4().hex[:8]}",
            prompt_version="v1",
            model="test-model",
        )
        await bank.insert_questions([q_optics])
        await uow.session.commit()

    # 3. Configure all Academics services
    quiz_service = QuizService(session_factory=session_factory)
    set_quiz_service(quiz_service)

    flashcard_service = FlashcardService(
        session_factory=session_factory,
    )
    set_flashcard_service(flashcard_service)

    study_plan_service = StudyPlanService(
        session_factory=session_factory,
    )
    set_study_plan_service(study_plan_service)

    progress_service = ProgressService(session_factory=session_factory)
    set_progress_service(progress_service)

    brief_service = TopicBriefService(
        wikipedia=E2EMockWikipediaClient(),
    )
    set_brief_service(brief_service)

    # 4. Wire MCP App & Streamable HTTP client
    jwk_dict = dict(json.loads(RSAAlgorithm.to_jwk(e2e_rsa_key.public_key())))
    jwk_dict["kid"] = "sec-test-key"
    jwks = {"keys": [jwk_dict]}
    transport_mock = httpx.MockTransport(lambda _: httpx.Response(200, json=jwks))
    jwks_client = httpx.AsyncClient(transport=transport_mock)

    jwt_validator = JWTValidator(
        issuer="https://auth.example.com",
        audience="sahayak-api",
        jwks_url="https://auth.example.com/.well-known/jwks.json",
        http_client=jwks_client,
    )

    module = AcademicsModule()
    registry = ModuleRegistry()
    registry._modules["academics"] = module

    deps = Deps(session_factory=session_factory)
    app = create_app(registry=registry, deps=deps, jwt_validator=jwt_validator)

    token = make_test_token(e2e_rsa_key, sub=user_sub)
    headers = {"Authorization": f"Bearer {token}"}
    asgi_transport = httpx.ASGITransport(app=app)

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=asgi_transport, base_url="http://testserver", headers=headers
        ) as client,
        streamable_http_client("http://testserver/mcp", http_client=cast(Any, client)) as (
            r,
            w,
        ),
        ClientSession(r, w) as session,
    ):
        init_res = await session.initialize()
        assert init_res.protocol_version == "2025-11-25"

        # Verify tool discovery includes all 6 tools
        tools_list = await session.list_tools()
        registered_names = {t.name for t in tools_list.tools}
        assert registered_names == {
            "quiz_start",
            "quiz_answer",
            "flashcards",
            "study_plan",
            "progress_report",
            "topic_brief",
        }

        # =======================================================================
        # DIALOG 1 — Interactive Quiz & Progress
        # PRD §2.1:
        # "Alexa, ask Sahayak to quiz me on photosynthesis." -> quiz_start
        # "Option B." -> quiz_answer
        # "How am I doing?" -> progress_report
        # "Quiz me on my weak topics." -> quiz_start(source=weak_topics)
        # =======================================================================

        # Turn 1: "Alexa, ask Sahayak to quiz me on photosynthesis."
        res1 = await session.call_tool(
            "quiz_start",
            arguments={"topic": "photosynthesis", "num_questions": 3},
        )
        assert not res1.is_error
        data1 = json.loads(getattr(res1.content[0], "text", "{}"))
        assert data1["ok"] is True
        quiz_id = data1["data"]["quiz_id"]
        assert quiz_id
        # Ensure correct answer is not revealed in question turn
        assert "correct answer" not in data1["spoken_summary"].lower()
        assert "correct_key" not in data1["data"]
        assert "explanation" not in data1["data"]
        assert data1["data"]["number"] == 1
        assert data1["data"]["total"] == 3

        # Turn 2: "Option B."
        res2 = await session.call_tool(
            "quiz_answer",
            arguments={"quiz_id": quiz_id, "answer": "Option B"},
        )
        assert not res2.is_error
        data2 = json.loads(getattr(res2.content[0], "text", "{}"))
        assert data2["ok"] is True
        assert data2["data"]["correct"] is True
        assert data2["data"]["score"]["correct"] == 1
        assert_voice_summary_valid(data2["spoken_summary"])

        # Answer question 2 ("Option B")
        res3 = await session.call_tool(
            "quiz_answer",
            arguments={"quiz_id": quiz_id, "answer": "Option B"},
        )
        data3 = json.loads(getattr(res3.content[0], "text", "{}"))
        assert data3["ok"] is True
        assert data3["data"]["correct"] is True
        assert data3["data"]["score"]["correct"] == 2

        # Answer question 3 ("Option A") - finish quiz
        res4 = await session.call_tool(
            "quiz_answer",
            arguments={"quiz_id": quiz_id, "answer": "Option A"},
        )
        data4 = json.loads(getattr(res4.content[0], "text", "{}"))
        assert data4["ok"] is True
        assert data4["data"]["correct"] is True
        assert data4["data"]["finished"] is True
        assert data4["data"]["score"]["correct"] == 3
        assert_voice_summary_valid(data4["spoken_summary"])

        # Dispatch academics.quiz.finished domain event
        now = datetime.now(UTC)
        quiz_event = DomainEvent(
            id=uuid.uuid4(),
            aggregate="quiz",
            type="academics.quiz.finished",
            created_at=now,
            payload={
                "quiz_id": quiz_id,
                "user_id": str(user_id),
                "topic_key": "photosynthesis",
                "topic_name": "Photosynthesis",
                "score": 3,
                "total_questions": 3,
                "percentage": 100.0,
            },
        )
        await module.on_event(quiz_event)

        # Seed low score in Optics to make Optics a weak topic
        optics_event = DomainEvent(
            id=uuid.uuid4(),
            aggregate="quiz",
            type="academics.quiz.finished",
            created_at=now,
            payload={
                "quiz_id": str(uuid.uuid4()),
                "user_id": str(user_id),
                "topic_key": "optics",
                "topic_name": "Optics",
                "score": 1,
                "total_questions": 5,
                "percentage": 20.0,
            },
        )
        await module.on_event(optics_event)

        # Turn 3: "How am I doing?" -> progress_report
        res_prog = await session.call_tool(
            "progress_report",
            arguments={"scope": "summary"},
        )
        data_prog = json.loads(getattr(res_prog.content[0], "text", "{}"))
        assert data_prog["ok"] is True
        assert_voice_summary_valid(data_prog["spoken_summary"])
        assert data_prog["data"]["streak"]["current_streak"] >= 1
        assert len(data_prog["data"]["weak_topics"]) >= 1
        assert data_prog["data"]["weak_topics"][0]["topic"] == "Optics"

        # Turn 4: "Quiz me on my weak topics." -> quiz_start(source=weak_topics)
        res_weak = await session.call_tool(
            "quiz_start",
            arguments={"source": "weak_topics", "num_questions": 3},
        )
        data_weak = json.loads(getattr(res_weak.content[0], "text", "{}"))
        assert data_weak["ok"] is True
        assert data_weak["data"]["topic"] == "Optics"
        assert_voice_summary_valid(data_weak["spoken_summary"])

        # =======================================================================
        # DIALOG 2 — Flashcards Spaced Repetition
        # PRD §2.1:
        # "Add a flashcard: capital of Australia is Canberra." -> flashcards(action=add)
        # "Review my flashcards." -> flashcards(action=review_next) then grade
        # =======================================================================

        # Turn 1: "Add a flashcard: capital of Australia is Canberra."
        res_fc1 = await session.call_tool(
            "flashcards",
            arguments={
                "action": "add",
                "front": "capital of Australia",
                "back": "Canberra",
                "deck": "Geography",
            },
        )
        data_fc1 = json.loads(getattr(res_fc1.content[0], "text", "{}"))
        assert data_fc1["ok"] is True
        card_id = data_fc1["data"]["card"]["card_id"]
        assert card_id
        assert_voice_summary_valid(data_fc1["spoken_summary"])

        # Turn 2: "Review my flashcards."
        res_fc2 = await session.call_tool(
            "flashcards",
            arguments={"action": "review_next"},
        )
        data_fc2 = json.loads(getattr(res_fc2.content[0], "text", "{}"))
        assert data_fc2["ok"] is True
        assert data_fc2["data"]["card"]["front"] == "capital of Australia"
        assert_voice_summary_valid(data_fc2["spoken_summary"])

        # Turn 3: Grade the flashcard "good"
        res_fc3 = await session.call_tool(
            "flashcards",
            arguments={
                "action": "grade",
                "card_id": card_id,
                "rating": "good",
            },
        )
        data_fc3 = json.loads(getattr(res_fc3.content[0], "text", "{}"))
        assert data_fc3["ok"] is True
        assert data_fc3["data"]["card"]["repetitions"] == 1
        assert_voice_summary_valid(data_fc3["spoken_summary"])

        # =======================================================================
        # DIALOG 3 — Study Plan
        # PRD §2.1:
        # "My chemistry exam is on the 15th. Make a study plan." -> study_plan(action=create)
        # "What should I study today?" -> study_plan(action=today)
        # =======================================================================

        exam_date = (datetime.now(UTC).date() + timedelta(days=10)).isoformat()

        # Turn 1: "My chemistry exam is on the 15th. Make a study plan."
        res_sp1 = await session.call_tool(
            "study_plan",
            arguments={
                "action": "create",
                "goal": "chemistry exam",
                "exam_date": exam_date,
                "topics": ["Organic Chemistry", "Thermodynamics"],
                "hours_per_day": 2,
            },
        )
        data_sp1 = json.loads(getattr(res_sp1.content[0], "text", "{}"))
        assert data_sp1["ok"] is True
        assert len(data_sp1["data"]["tasks"]) > 0
        assert_voice_summary_valid(data_sp1["spoken_summary"])

        # Turn 2: "What should I study today?"
        res_sp2 = await session.call_tool(
            "study_plan",
            arguments={"action": "today"},
        )
        data_sp2 = json.loads(getattr(res_sp2.content[0], "text", "{}"))
        assert data_sp2["ok"] is True
        assert "tasks" in data_sp2["data"]
        assert_voice_summary_valid(data_sp2["spoken_summary"])

        # =======================================================================
        # DIALOG 4 — Topic Brief
        # PRD §2.1:
        # "Give me a quick brief on the French Revolution." -> topic_brief
        # =======================================================================

        res_tb = await session.call_tool(
            "topic_brief",
            arguments={"topic": "French Revolution", "length": "short"},
        )
        data_tb = json.loads(getattr(res_tb.content[0], "text", "{}"))
        assert data_tb["ok"] is True
        assert_voice_summary_valid(data_tb["spoken_summary"])
        assert len(data_tb["data"]["sources"]) >= 1
        assert data_tb["data"]["sources"][0]["title"] == "French Revolution"
        assert "French Revolution" in data_tb["data"]["brief"]
