"""Contract tests for quiz_answer MCP tool over Streamable HTTP (T3.7)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import httpx
import pytest
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.config import get_settings
from sahayak.core.db.session import UnitOfWork
from sahayak.core.module import Deps, ModuleRegistry
from sahayak.main import create_app
from sahayak.modules.academics.adapters.question_bank import SQLAlchemyQuestionBank
from sahayak.modules.academics.models import DifficultyLevel, Question
from sahayak.modules.academics.service.quiz import QuizService
from sahayak.modules.academics.tools.quiz import set_quiz_service


@pytest.mark.asyncio
async def test_quiz_5_question_flow_contract() -> None:
    """Full 5-question MCP tool contract flow: correct, incorrect, ambiguous, replay, finished."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    test_id = uuid.uuid4().hex[:6]
    topic_slug = f"cell-biology-{test_id}"
    topic_display = f"Cell Biology {test_id}"

    # 1. Seed 6 approved questions
    try:
        async with UnitOfWork(session_factory) as uow:
            bank = SQLAlchemyQuestionBank(uow.session)
            topic = await bank.get_or_create_topic(topic_slug, topic_display)
            questions = [
                Question(
                    topic_id=topic.id,
                    difficulty=DifficultyLevel.MEDIUM,
                    stem=f"Cell biology {test_id} question {i}?",
                    options={
                        "A": f"OptA {i}",
                        "B": f"OptB {i}",
                        "C": f"OptC {i}",
                        "D": f"OptD {i}",
                    },
                    correct_key="A",
                    explanation=f"Cell biology explanation {i}.",
                    content_hash=f"cell_{test_id}_{i}_{uuid.uuid4().hex[:6]}",
                    prompt_version="v1",
                    model="test-model",
                )
                for i in range(6)
            ]
            await bank.insert_questions(questions)
            await uow.session.commit()

        registry = ModuleRegistry()
        registry.load(("academics",))

        deps = Deps(session_factory=session_factory)
        app = create_app(registry=registry, deps=deps)

        # 2. Configure quiz service with controllable clock AFTER create_app
        current_time = datetime(2026, 10, 23, 16, 0, tzinfo=UTC)
        service = QuizService(
            session_factory=session_factory,
            generator=None,
            clock=lambda: current_time,
            quiz_ttl_minutes=15,
        )
        set_quiz_service(service)

        transport = httpx.ASGITransport(app=app)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(transport=transport, base_url="http://testserver") as http_client,
            streamable_http_client("http://testserver/mcp", http_client=cast(Any, http_client)) as (
                read_stream,
                write_stream,
            ),
            ClientSession(read_stream, write_stream) as session,
        ):
            await session.initialize()

            # 3. Start a 5-question quiz
            start_res = await session.call_tool(
                "quiz_start",
                arguments={"topic": topic_display, "num_questions": 5},
            )
            start_envelope = json.loads(getattr(start_res.content[0], "text", "{}"))
            assert start_envelope["ok"] is True
            quiz_id = start_envelope["data"]["quiz_id"]
            assert start_envelope["data"]["total"] == 5
            assert start_envelope["data"]["number"] == 1

            # 4. Question 1: Answer correctly ("Option A")
            q1_res = await session.call_tool(
                "quiz_answer",
                arguments={"quiz_id": quiz_id, "answer": "Option A"},
            )
            q1_envelope = json.loads(getattr(q1_res.content[0], "text", "{}"))
            assert q1_envelope["ok"] is True
            assert q1_envelope["data"]["correct"] is True
            assert q1_envelope["data"]["correct_key"] == "A"
            assert q1_envelope["data"]["score"]["correct"] == 1
            assert q1_envelope["data"]["score"]["answered"] == 1
            assert q1_envelope["data"]["score"]["total"] == 5
            assert q1_envelope["data"]["finished"] is False
            assert q1_envelope["data"]["next"]["number"] == 2

            # 5. Question 2: Ambiguous answer ("A or B") -> invalid_input, does NOT consume attempt
            ambig_res = await session.call_tool(
                "quiz_answer",
                arguments={"quiz_id": quiz_id, "answer": "A or B"},
            )
            ambig_envelope = json.loads(getattr(ambig_res.content[0], "text", "{}"))
            assert ambig_envelope["ok"] is False
            assert ambig_envelope["error_code"] == "invalid_input"
            assert "I'm not sure which option you meant" in ambig_envelope["spoken_summary"]

            # 6. Question 2: Re-answer with incorrect answer ("Option B")
            q2_res = await session.call_tool(
                "quiz_answer",
                arguments={"quiz_id": quiz_id, "answer": "Option B"},
            )
            q2_envelope = json.loads(getattr(q2_res.content[0], "text", "{}"))
            assert q2_envelope["ok"] is True
            assert q2_envelope["data"]["correct"] is False
            assert q2_envelope["data"]["score"]["correct"] == 1
            assert q2_envelope["data"]["score"]["answered"] == 2
            assert q2_envelope["data"]["next"]["number"] == 3

            # 7. Question 3: Answer with request_id for idempotency test
            req_id = str(uuid.uuid4())
            q3_res = await session.call_tool(
                "quiz_answer",
                arguments={"quiz_id": quiz_id, "answer": "Option A", "request_id": req_id},
            )
            q3_envelope = json.loads(getattr(q3_res.content[0], "text", "{}"))
            assert q3_envelope["ok"] is True
            assert q3_envelope["data"]["score"]["correct"] == 2
            assert q3_envelope["data"]["score"]["answered"] == 3

            # 8. Replayed request_id produces identical cached response
            replay_res = await session.call_tool(
                "quiz_answer",
                arguments={"quiz_id": quiz_id, "answer": "Option A", "request_id": req_id},
            )
            replay_envelope = json.loads(getattr(replay_res.content[0], "text", "{}"))
            assert replay_envelope["ok"] is True
            assert replay_envelope["data"] == q3_envelope["data"]
            assert replay_envelope["spoken_summary"] == q3_envelope["spoken_summary"]

            # 9. Question 4: Answer correctly
            q4_res = await session.call_tool(
                "quiz_answer",
                arguments={"quiz_id": quiz_id, "answer": "Option A"},
            )
            q4_envelope = json.loads(getattr(q4_res.content[0], "text", "{}"))
            assert q4_envelope["ok"] is True
            assert q4_envelope["data"]["score"]["answered"] == 4
            assert q4_envelope["data"]["next"]["number"] == 5

            # 10. Question 5 (final question): Answer correctly -> finishes quiz
            q5_res = await session.call_tool(
                "quiz_answer",
                arguments={"quiz_id": quiz_id, "answer": "Option A"},
            )
            q5_envelope = json.loads(getattr(q5_res.content[0], "text", "{}"))
            assert q5_envelope["ok"] is True
            assert q5_envelope["data"]["finished"] is True
            assert q5_envelope["data"]["next"] is None
            assert q5_envelope["data"]["score"]["correct"] == 4
            assert q5_envelope["data"]["score"]["answered"] == 5
            assert "You finished the quiz" in q5_envelope["spoken_summary"]

            # 11. Trying to answer after completed returns invalid_input
            post_res = await session.call_tool(
                "quiz_answer",
                arguments={"quiz_id": quiz_id, "answer": "Option A"},
            )
            post_envelope = json.loads(getattr(post_res.content[0], "text", "{}"))
            assert post_envelope["ok"] is False
            assert post_envelope["error_code"] == "invalid_input"

            # 12. Test expiry on a new quiz session
            start2_res = await session.call_tool(
                "quiz_start",
                arguments={"topic": topic_display, "num_questions": 3},
            )
            start2_envelope = json.loads(getattr(start2_res.content[0], "text", "{}"))
            quiz2_id = start2_envelope["data"]["quiz_id"]

            # Fast-forward clock past 15 min TTL
            current_time = current_time + timedelta(minutes=25)

            exp_res = await session.call_tool(
                "quiz_answer",
                arguments={"quiz_id": quiz2_id, "answer": "Option A"},
            )
            exp_envelope = json.loads(getattr(exp_res.content[0], "text", "{}"))
            assert exp_envelope["ok"] is False
            assert exp_envelope["error_code"] == "not_found"
            assert "expired" in exp_envelope["spoken_summary"].lower()

    finally:
        await engine.dispose()
