"""Contract tests for progress_report MCP tool over Streamable HTTP (T3.13)."""

from __future__ import annotations

import json
import time
import uuid
from datetime import UTC, datetime
from typing import Any, cast

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.auth.jwt import JWTValidator
from sahayak.core.config import get_settings
from sahayak.core.events import DomainEvent
from sahayak.core.module import Deps, ModuleRegistry
from sahayak.main import create_app
from sahayak.modules.academics.service.progress import ProgressService
from sahayak.modules.academics.tools.progress import set_progress_service
from tests.security.isolation import ISOLATION_REGISTRY, assert_user_isolation


@pytest.fixture(scope="module")
def contract_rsa_key() -> rsa.RSAPrivateKey:
    """RSA private key for signing test JWTs."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def make_test_token(
    key: rsa.RSAPrivateKey,
    *,
    sub: str,
    scope: str = "academics:read",
) -> str:
    """Generate a signed test JWT for MCP contract testing."""
    now = int(time.time())
    payload = {
        "sub": sub,
        "iss": "https://auth.example.com",
        "aud": "sahayak-api",
        "exp": now + 3600,
        "iat": now,
        "nbf": now,
        "scope": scope,
    }
    return jwt.encode(payload, key, algorithm="RS256", headers={"kid": "sec-test-key"})


@pytest.mark.asyncio
async def test_progress_report_mcp_contract_full_lifecycle(
    contract_rsa_key: rsa.RSAPrivateKey,
) -> None:
    """Contract test for progress_report over Streamable HTTP:

    1. Call progress_report initially.
    2. Dispatch a quiz.finished event.
    3. Re-call progress_report (summary, weak_topics, streak, weekly).
    4. Verify user isolation.
    """
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    service = ProgressService(session_factory=session_factory)
    set_progress_service(service)

    # Seed questions for isolation check which calls quiz_start on General Science
    from sahayak.core.db.session import UnitOfWork
    from sahayak.modules.academics.adapters.question_bank import SQLAlchemyQuestionBank
    from sahayak.modules.academics.models import DifficultyLevel, Question

    async with UnitOfWork(session_factory) as uow:
        bank = SQLAlchemyQuestionBank(uow.session)
        topic = await bank.get_or_create_topic("general-science", "General Science")
        seeded = [
            Question(
                topic_id=topic.id,
                difficulty=DifficultyLevel.MEDIUM,
                stem=f"General science question {i}?",
                options={"A": "Alpha", "B": "Beta", "C": "Gamma", "D": "Delta"},
                correct_key="A",
                explanation="General science fact",
                content_hash=f"gen_sci_prog_{uuid.uuid4().hex[:12]}",
                prompt_version="v1",
                model="test-model",
            )
            for i in range(3)
        ]
        await bank.insert_questions(seeded)
        await uow.session.commit()

    # Configure JWT validator with mock JWKS
    jwk_dict = dict(json.loads(RSAAlgorithm.to_jwk(contract_rsa_key.public_key())))
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

    user_sub = f"progress-user-{uuid.uuid4()}"
    token = make_test_token(contract_rsa_key, sub=user_sub)

    registry = ModuleRegistry()
    registry.load(("academics",))
    deps = Deps(session_factory=session_factory)
    app = create_app(
        registry=registry,
        deps=deps,
        jwt_validator=jwt_validator,
    )

    asgi_transport = httpx.ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {token}"}

    try:
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
            await session.initialize()

            # 1. Initial report - empty stats
            res_init = await session.call_tool(
                "progress_report",
                arguments={"scope": "summary"},
            )
            data_init = json.loads(getattr(res_init.content[0], "text", "{}"))
            assert data_init.get("ok") is True
            assert "haven't completed any quizzes yet" in data_init.get("spoken_summary", "")

            # 2. Get user_id from User model
            from sahayak.core.db.session import UnitOfWork
            from sahayak.shared.users.models import UserIdentity

            async with UnitOfWork(session_factory) as uow:
                stmt = select(UserIdentity.user_id).where(UserIdentity.subject == user_sub)
                u_res = await uow.session.execute(stmt)
                user_id = u_res.scalar_one()

            # 3. Simulate quiz.finished event
            quiz_event = DomainEvent(
                id=uuid.uuid4(),
                aggregate="quiz",
                type="academics.quiz.finished",
                payload={
                    "quiz_id": str(uuid.uuid4()),
                    "user_id": str(user_id),
                    "topic_key": "photosynthesis",
                    "topic_name": "Photosynthesis",
                    "score": 3,
                    "total_questions": 5,
                    "percentage": 60.0,
                },
                created_at=datetime.now(UTC),
            )
            await service.handle_quiz_finished(quiz_event)

            # 4. Scope: summary
            res_summary = await session.call_tool(
                "progress_report",
                arguments={"scope": "summary"},
            )
            data_summary = json.loads(getattr(res_summary.content[0], "text", "{}"))
            assert data_summary.get("ok") is True
            summary_payload = data_summary.get("data", {})
            assert summary_payload.get("streak", {}).get("current_streak") == 1
            assert summary_payload.get("total_questions") == 5
            assert "Photosynthesis" in data_summary.get("spoken_summary", "")

            # 5. Scope: weak_topics
            res_weak = await session.call_tool(
                "progress_report",
                arguments={"scope": "weak_topics"},
            )
            data_weak = json.loads(getattr(res_weak.content[0], "text", "{}"))
            assert data_weak.get("ok") is True
            weak_topics = data_weak.get("data", {}).get("weak_topics", [])
            assert len(weak_topics) >= 1
            assert weak_topics[0].get("topic") == "Photosynthesis"

            # 6. Scope: streak
            res_streak = await session.call_tool(
                "progress_report",
                arguments={"scope": "streak"},
            )
            data_streak = json.loads(getattr(res_streak.content[0], "text", "{}"))
            assert data_streak.get("ok") is True
            assert "1 day study streak" in data_streak.get("spoken_summary", "")

            # 7. Scope: weekly
            res_weekly = await session.call_tool(
                "progress_report",
                arguments={"scope": "weekly"},
            )
            data_weekly = json.loads(getattr(res_weekly.content[0], "text", "{}"))
            assert data_weekly.get("ok") is True
            weekly_payload = data_weekly.get("data", {}).get("weekly", {})
            assert weekly_payload.get("active_days") == 1

            # 8. User isolation check
            await assert_user_isolation(
                ISOLATION_REGISTRY["progress_report"], app, contract_rsa_key
            )

    finally:
        set_progress_service(None)
        await jwks_client.aclose()
        await engine.dispose()


@pytest.mark.asyncio
async def test_progress_report_mcp_contract_anonymous_rejected() -> None:
    """Anonymous callers cannot use progress_report tool."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    registry = ModuleRegistry()
    registry.load(("academics",))
    deps = Deps(session_factory=session_factory)
    app = create_app(registry=registry, deps=deps)

    asgi_transport = httpx.ASGITransport(app=app)
    try:
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(transport=asgi_transport, base_url="http://testserver") as client,
            streamable_http_client("http://testserver/mcp", http_client=cast(Any, client)) as (
                r,
                w,
            ),
            ClientSession(r, w) as session,
        ):
            await session.initialize()
            res = await session.call_tool("progress_report", arguments={"scope": "summary"})
            data = json.loads(getattr(res.content[0], "text", "{}"))
            assert data.get("ok") is False
            assert data.get("error_code") == "auth_required"
    finally:
        await engine.dispose()
