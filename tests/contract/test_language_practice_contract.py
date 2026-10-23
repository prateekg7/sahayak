"""Contract tests for language_practice MCP tool over Streamable HTTP (T11.2)."""

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
from sahayak.modules.language.service.practice import LanguagePracticeService
from sahayak.modules.language.tools.language_practice import set_language_practice_service
from sahayak.shared.users.models import User


@pytest.fixture(scope="module")
def practice_contract_rsa_key() -> rsa.RSAPrivateKey:
    """RSA private key for signing test JWTs."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def make_test_token(
    key: rsa.RSAPrivateKey,
    *,
    sub: str,
    scope: str = "",
) -> str:
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
    return jwt.encode(payload, key, algorithm="RS256", headers={"kid": "sec-practice-key"})


@pytest.mark.asyncio
async def test_language_practice_contract_full_lifecycle(
    practice_contract_rsa_key: rsa.RSAPrivateKey,
) -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    jwk_dict = dict(json.loads(RSAAlgorithm.to_jwk(practice_contract_rsa_key.public_key())))
    jwk_dict["kid"] = "sec-practice-key"
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
    registry.load(("language",))
    deps = Deps(session_factory=session_factory)
    app = create_app(
        registry=registry,
        deps=deps,
        jwt_validator=validator,
    )

    practice_svc = LanguagePracticeService(session_factory=session_factory)
    set_language_practice_service(practice_svc)

    user_id = uuid.uuid4()
    async with UnitOfWork(session_factory) as uow:
        uow.session.add(User(id=user_id))
        await uow.session.commit()

    token = make_test_token(practice_contract_rsa_key, sub=str(user_id))
    headers = {"Authorization": f"Bearer {token}"}
    asgi_transport = httpx.ASGITransport(app=app)

    try:
        async with app.router.lifespan_context(app):
            # 1. Anonymous call fails with auth_required
            async with (
                httpx.AsyncClient(
                    transport=asgi_transport, base_url="http://testserver"
                ) as anon_client,
                streamable_http_client(
                    "http://testserver/mcp", http_client=cast(Any, anon_client)
                ) as (r_anon, w_anon),
                ClientSession(r_anon, w_anon) as anon_session,
            ):
                await anon_session.initialize()
                anon_res = await anon_session.call_tool(
                    "language_practice", {"action": "start_conversation"}
                )
                anon_data = json.loads(getattr(anon_res.content[0], "text", "{}"))
                assert anon_data.get("ok") is False
                assert anon_data.get("error_code") == "auth_required"

            # 2. Authenticated lifecycle
            async with (
                httpx.AsyncClient(
                    transport=asgi_transport,
                    base_url="http://testserver",
                    headers=headers,
                ) as auth_client,
                streamable_http_client(
                    "http://testserver/mcp", http_client=cast(Any, auth_client)
                ) as (r_auth, w_auth),
                ClientSession(r_auth, w_auth) as session,
            ):
                await session.initialize()

                # 2a. Start conversation
                res_start = await session.call_tool(
                    "language_practice",
                    {
                        "action": "start_conversation",
                        "language": "spanish",
                        "scenario": "ordering_coffee",
                    },
                )
                data_start = json.loads(getattr(res_start.content[0], "text", "{}"))
                assert data_start.get("ok") is True
                assert len(data_start.get("spoken_summary", "")) <= 300
                session_info = data_start.get("data", {}).get("session")
                assert session_info is not None
                session_id = session_info.get("id")
                assert session_id is not None

                # 2b. Reply in conversation
                res_reply = await session.call_tool(
                    "language_practice",
                    {
                        "action": "reply",
                        "session_id": session_id,
                        "user_message": "Yo quiero un cafe con leche por favor.",
                    },
                )
                data_reply = json.loads(getattr(res_reply.content[0], "text", "{}"))
                assert data_reply.get("ok") is True
                assert data_reply.get("data", {}).get("partner_response") is not None
                assert len(data_reply.get("spoken_summary", "")) <= 300

                # 2c. Translate and explain
                res_trans = await session.call_tool(
                    "language_practice",
                    {
                        "action": "translate_explain",
                        "query": "Where is the bathroom?",
                        "target_language": "spanish",
                    },
                )
                data_trans = json.loads(getattr(res_trans.content[0], "text", "{}"))
                assert data_trans.get("ok") is True
                assert data_trans.get("data", {}).get("translate_explain") is not None
                assert len(data_trans.get("spoken_summary", "")) <= 300

                # 2d. Conclude conversation
                res_end = await session.call_tool(
                    "language_practice",
                    {
                        "action": "end",
                        "session_id": session_id,
                    },
                )
                data_end = json.loads(getattr(res_end.content[0], "text", "{}"))
                assert data_end.get("ok") is True
                assert data_end.get("data", {}).get("session", {}).get("status") == "completed"

    finally:
        await jwks_client.aclose()
        await engine.dispose()
