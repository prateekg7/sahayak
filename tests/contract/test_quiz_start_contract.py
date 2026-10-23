"""Contract tests for quiz_start MCP tool over Streamable HTTP (T3.6)."""

from __future__ import annotations

import json
import uuid
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
async def test_quiz_start_mcp_tool_contract() -> None:
    """Full HTTP contract test for quiz_start: schema, envelope, and answer safety."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    # Seed 3 questions in DB for "Cell Biology"
    try:
        async with UnitOfWork(session_factory) as uow:
            bank = SQLAlchemyQuestionBank(uow.session)
            topic = await bank.get_or_create_topic("cell-biology", "Cell Biology")
            questions = [
                Question(
                    topic_id=topic.id,
                    difficulty=DifficultyLevel.MEDIUM,
                    stem=f"Cell biology question {i}?",
                    options={"A": "Mitochondria", "B": "Ribosome", "C": "Nucleus", "D": "Golgi"},
                    correct_key="A",
                    explanation="Cell biology secret explanation.",
                    content_hash=f"cell_{uuid.uuid4().hex[:12]}",
                    prompt_version="v1",
                    model="test-model",
                )
                for i in range(4)
            ]
            await bank.insert_questions(questions)
            await uow.session.commit()

        # Configure quiz service
        service = QuizService(
            session_factory=session_factory,
            generator=None,
        )
        set_quiz_service(service)

        registry = ModuleRegistry()
        registry.load(("academics",))

        deps = Deps(session_factory=session_factory)
        app = create_app(registry=registry, deps=deps)

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
            # 1. Initialize
            init_res = await session.initialize()
            assert init_res.protocol_version == "2025-11-25"

            # 2. List tools includes quiz_start
            tools_res = await session.list_tools()
            tool_names = [t.name for t in tools_res.tools]
            assert "quiz_start" in tool_names

            # 3. Call quiz_start
            call_res = await session.call_tool(
                "quiz_start",
                arguments={
                    "topic": "Cell Biology",
                    "num_questions": 3,
                    "request_id": "req-quiz-contract-001",
                },
            )
            assert not call_res.is_error
            assert len(call_res.content) > 0

            first_block = call_res.content[0]
            text_val = getattr(first_block, "text", "")
            payload = json.loads(text_val)

            # 4. Standard Result Envelope checks
            assert payload["ok"] is True
            assert "spoken_summary" in payload
            assert "Cell Biology" in payload["spoken_summary"]
            assert "Question 1" in payload["spoken_summary"]

            # Voice UX checks: no markdown asterisks or links in speech
            assert "*" not in payload["spoken_summary"]
            assert "http" not in payload["spoken_summary"]

            # Data checks
            data = payload["data"]
            assert "quiz_id" in data
            # quiz_id must be valid UUID
            uuid.UUID(data["quiz_id"])
            assert data["number"] == 1
            assert data["total"] == 3
            assert data["topic"] == "Cell Biology"
            assert data["difficulty"] == "medium"
            assert "question" in data
            assert len(data["options"]) == 4

            # CRITICAL SECURITY RULE: never leak correct answer or explanation
            assert "correct_key" not in data
            assert "correct_answer" not in data
            assert "explanation" not in data
            for opt in data["options"]:
                assert "key" in opt
                assert "text" in opt
                assert "is_correct" not in opt

            # 5. Idempotent replay: identical request_id returns identical quiz_id
            replay_res = await session.call_tool(
                "quiz_start",
                arguments={
                    "topic": "Cell Biology",
                    "num_questions": 3,
                    "request_id": "req-quiz-contract-001",
                },
            )
            replay_payload = json.loads(getattr(replay_res.content[0], "text", "{}"))
            assert replay_payload["ok"] is True
            assert replay_payload["data"]["quiz_id"] == data["quiz_id"]

    finally:
        await engine.dispose()
