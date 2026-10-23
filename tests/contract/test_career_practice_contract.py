"""Contract tests for career_practice MCP tool over Streamable HTTP (T8.3)."""

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
from sahayak.modules.career.service.practice import CareerPracticeService
from sahayak.modules.career.tools.career_practice import set_practice_service
from sahayak.shared.users.models import User


@pytest.fixture(scope="module")
def practice_contract_rsa_key() -> rsa.RSAPrivateKey:
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
async def test_career_practice_contract_full_lifecycle(
    practice_contract_rsa_key: rsa.RSAPrivateKey,
) -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    jwk_dict = dict(json.loads(RSAAlgorithm.to_jwk(practice_contract_rsa_key.public_key())))
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

    practice_service = CareerPracticeService(session_factory=session_factory)
    set_practice_service(practice_service)

    user_a = uuid.uuid4()
    async with UnitOfWork(session_factory) as uow:
        uow.session.add(User(id=user_a))
        await uow.session.commit()

    token_a = make_test_token(practice_contract_rsa_key, sub=str(user_a))
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
                    "career_practice", arguments={"action": "daily_question"}
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
                    "http://testserver/mcp",
                    http_client=cast(Any, client_auth),
                ) as (
                    r_auth,
                    w_auth,
                ),
                ClientSession(r_auth, w_auth) as session_auth,
            ):
                await session_auth.initialize()

                # Action: improve_bullet
                res_imp = await session_auth.call_tool(
                    "career_practice",
                    arguments={
                        "action": "improve_bullet",
                        "bullet": "Architected event-driven microservices reducing latency by 40%",
                    },
                )
                data_imp = json.loads(getattr(res_imp.content[0], "text", "{}"))
                assert data_imp.get("ok") is True
                assert "xyz_formula" in data_imp.get("data", {})
                assert len(data_imp.get("data", {}).get("improved_variations", [])) >= 2
                assert len(data_imp.get("spoken_summary", "")) <= 300

                # Action: daily_question
                res_q = await session_auth.call_tool(
                    "career_practice",
                    arguments={"action": "daily_question"},
                )
                data_q = json.loads(getattr(res_q.content[0], "text", "{}"))
                assert data_q.get("ok") is True
                q_key = data_q.get("data", {}).get("question_key")
                assert q_key is not None
                assert len(data_q.get("spoken_summary", "")) <= 300

                # Action: check_answer
                res_ans = await session_auth.call_tool(
                    "career_practice",
                    arguments={
                        "action": "check_answer",
                        "question_key": q_key,
                        "answer": "The situation, task, action taken, and measurable result.",
                    },
                )
                data_ans = json.loads(getattr(res_ans.content[0], "text", "{}"))
                assert data_ans.get("ok") is True
                assert data_ans.get("data", {}).get("is_correct") is True
                assert data_ans.get("data", {}).get("stats", {}).get("total_attempts") == 1
                assert len(data_ans.get("spoken_summary", "")) <= 300

                # Action: improve_bullet missing bullet
                res_err1 = await session_auth.call_tool(
                    "career_practice",
                    arguments={"action": "improve_bullet"},
                )
                data_err1 = json.loads(getattr(res_err1.content[0], "text", "{}"))
                assert data_err1.get("ok") is False
                assert data_err1.get("error_code") == "invalid_input"

                # Action: unknown action
                res_err2 = await session_auth.call_tool(
                    "career_practice",
                    arguments={"action": "unknown_action"},
                )
                data_err2 = json.loads(getattr(res_err2.content[0], "text", "{}"))
                assert data_err2.get("ok") is False
                assert data_err2.get("error_code") == "invalid_input"
    finally:
        await engine.dispose()
