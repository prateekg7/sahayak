"""Contract tests for vocab MCP tool over Streamable HTTP (T11.1)."""

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
from sahayak.modules.language.service.vocab import VocabService
from sahayak.modules.language.tools.vocab import set_vocab_service
from sahayak.shared.users.models import User


@pytest.fixture(scope="module")
def vocab_contract_rsa_key() -> rsa.RSAPrivateKey:
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
    return jwt.encode(payload, key, algorithm="RS256", headers={"kid": "sec-test-key"})


@pytest.mark.asyncio
async def test_vocab_contract_full_lifecycle(
    vocab_contract_rsa_key: rsa.RSAPrivateKey,
) -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    jwk_dict = dict(json.loads(RSAAlgorithm.to_jwk(vocab_contract_rsa_key.public_key())))
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
    registry.load(("language",))
    deps = Deps(session_factory=session_factory)
    app = create_app(
        registry=registry,
        deps=deps,
        jwt_validator=validator,
    )

    vocab_svc = VocabService(session_factory=session_factory)
    set_vocab_service(vocab_svc)

    user_id = uuid.uuid4()
    async with UnitOfWork(session_factory) as uow:
        uow.session.add(User(id=user_id))
        await uow.session.commit()

    token = make_test_token(vocab_contract_rsa_key, sub=str(user_id))
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
                anon_res = await anon_session.call_tool("vocab", {"action": "word_of_day"})
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

                # 2a. Word of the day
                res_wod = await session.call_tool(
                    "vocab",
                    {"action": "word_of_day", "language": "spanish"},
                )
                data_wod = json.loads(getattr(res_wod.content[0], "text", "{}"))
                assert data_wod.get("ok") is True
                assert data_wod.get("data", {}).get("word") is not None
                uw_id = data_wod.get("data", {}).get("user_word", {}).get("id")
                assert uw_id is not None

                # 2b. Check stats
                res_stats = await session.call_tool(
                    "vocab",
                    {"action": "stats", "language": "spanish"},
                )
                data_stats = json.loads(getattr(res_stats.content[0], "text", "{}"))
                assert data_stats.get("ok") is True
                assert data_stats.get("data", {}).get("stats", {}).get("total_learned") >= 1

                # 2c. Grade the word
                res_grade = await session.call_tool(
                    "vocab",
                    {"action": "grade", "user_word_id": uw_id, "rating": "good"},
                )
                data_grade = json.loads(getattr(res_grade.content[0], "text", "{}"))
                assert data_grade.get("ok") is True
                assert data_grade.get("data", {}).get("user_word", {}).get("interval_days") == 1

                # 2d. Add custom word
                res_add = await session.call_tool(
                    "vocab",
                    {
                        "action": "add_word",
                        "language": "spanish",
                        "word": "libro",
                        "translation": "book",
                        "pronunciation_hint": "lee-broh",
                        "example_sentence": "Leo un libro interesante.",
                        "example_translation": "I read an interesting book.",
                    },
                )
                data_add = json.loads(getattr(res_add.content[0], "text", "{}"))
                assert data_add.get("ok") is True
                assert data_add.get("data", {}).get("word", {}).get("word") == "libro"

    finally:
        await jwks_client.aclose()
        await engine.dispose()
