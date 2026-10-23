"""Contract tests for interview_practice MCP tool over Streamable HTTP (T8.1)."""

from __future__ import annotations

import json
import time
import uuid
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
from sahayak.core.module import Deps, ModuleRegistry
from sahayak.main import create_app
from sahayak.modules.career.service.interview import InterviewService
from sahayak.modules.career.tools.interview_practice import set_interview_service
from sahayak.shared.users.models import User


@pytest.fixture(scope="module")
def career_contract_rsa_key() -> rsa.RSAPrivateKey:
    """RSA private key for signing test JWTs."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def make_test_token(
    key: rsa.RSAPrivateKey,
    *,
    sub: str,
    scope: str = "career.write",
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
async def test_interview_practice_contract_full_lifecycle(
    career_contract_rsa_key: rsa.RSAPrivateKey,
) -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    jwk_dict = dict(json.loads(RSAAlgorithm.to_jwk(career_contract_rsa_key.public_key())))
    jwk_dict["kid"] = "sec-test-key"
    jwks = {"keys": [jwk_dict]}

    transport_mock = httpx.MockTransport(lambda _: httpx.Response(200, json=jwks))
    jwks_client = httpx.AsyncClient(transport=transport_mock)

    validator = JWTValidator(
        issuer="https://auth.example.com",
        audience="sahayak-api",
        jwks_url="https://auth.example.com/.well-known/jwks.json",
        http_client=jwks_client,
    )

    registry = ModuleRegistry()
    registry.load(("academics", "productivity", "finance", "health", "career"))
    deps = Deps(session_factory=session_factory)
    app = create_app(
        registry=registry,
        deps=deps,
        jwt_validator=validator,
    )

    interview_service = InterviewService(session_factory=session_factory)
    set_interview_service(interview_service)

    user_a = uuid.uuid4()
    async with UnitOfWork(session_factory) as uow:
        uow.session.add(User(id=user_a))
        await uow.session.commit()

    token_a = make_test_token(career_contract_rsa_key, sub=str(user_a))
    headers_a = {"Authorization": f"Bearer {token_a}"}

    asgi_transport = httpx.ASGITransport(app=app)

    try:
        async with app.router.lifespan_context(app):
            # 1. Anonymous access rejected with auth_required
            async with (
                httpx.AsyncClient(transport=asgi_transport, base_url="http://testserver") as client,
                streamable_http_client("http://testserver/mcp", http_client=cast(Any, client)) as (
                    r_anon,
                    w_anon,
                ),
                ClientSession(r_anon, w_anon) as session_anon,
            ):
                await session_anon.initialize()
                res_anon = await session_anon.call_tool(
                    "interview_practice", arguments={"action": "start", "role": "Software Engineer"}
                )
                raw_anon = json.loads(getattr(res_anon.content[0], "text", "{}"))
                assert raw_anon.get("ok") is False
                assert raw_anon.get("error_code") == "auth_required"

            # 2. Authenticated user lifecycle
            async with (
                httpx.AsyncClient(
                    transport=asgi_transport, base_url="http://testserver", headers=headers_a
                ) as client_auth,
                streamable_http_client(
                    "http://testserver/mcp", http_client=cast(Any, client_auth)
                ) as (
                    r_auth,
                    w_auth,
                ),
                ClientSession(r_auth, w_auth) as session_auth,
            ):
                await session_auth.initialize()

                # Start session
                res_start = await session_auth.call_tool(
                    "interview_practice",
                    arguments={
                        "action": "start",
                        "role": "Software Engineer",
                        "level": "mid",
                        "total_questions": 2,
                    },
                )
                data_start = json.loads(getattr(res_start.content[0], "text", "{}"))
                assert data_start.get("ok") is True
                assert len(data_start.get("spoken_summary", "")) <= 300
                session_id = data_start.get("data", {}).get("session_id")
                assert session_id is not None
                assert data_start.get("data", {}).get("total_questions") == 2

                # Answer question 1
                res_ans1 = await session_auth.call_tool(
                    "interview_practice",
                    arguments={
                        "action": "answer",
                        "session_id": session_id,
                        "answer": "I debugged the memory leak and fixed the cyclic reference.",
                    },
                )
                data_ans1 = json.loads(getattr(res_ans1.content[0], "text", "{}"))
                assert data_ans1.get("ok") is True
                assert data_ans1.get("data", {}).get("status") == "in_progress"
                assert "score" in data_ans1.get("data", {})
                assert len(data_ans1.get("spoken_summary", "")) <= 300

                # Answer question 2 (completes session)
                res_ans2 = await session_auth.call_tool(
                    "interview_practice",
                    arguments={
                        "action": "answer",
                        "session_id": session_id,
                        "answer": "I designed the REST API with clear paths and versioning.",
                    },
                )
                data_ans2 = json.loads(getattr(res_ans2.content[0], "text", "{}"))
                assert data_ans2.get("ok") is True
                assert data_ans2.get("data", {}).get("status") == "completed"
                assert "overall_summary" in data_ans2.get("data", {})
                assert len(data_ans2.get("spoken_summary", "")) <= 300

                # Check history
                res_hist = await session_auth.call_tool(
                    "interview_practice",
                    arguments={"action": "history"},
                )
                data_hist = json.loads(getattr(res_hist.content[0], "text", "{}"))
                assert data_hist.get("ok") is True
                sessions = data_hist.get("data", {}).get("sessions", [])
                assert len(sessions) >= 1
                assert sessions[0]["session_id"] == session_id
                assert sessions[0]["status"] == "completed"

                # Validation error on missing session_id
                res_err = await session_auth.call_tool(
                    "interview_practice",
                    arguments={"action": "answer", "answer": "Missing session id"},
                )
                data_err = json.loads(getattr(res_err.content[0], "text", "{}"))
                assert data_err.get("ok") is False
                assert data_err.get("error_code") == "invalid_input"
    finally:
        await engine.dispose()
