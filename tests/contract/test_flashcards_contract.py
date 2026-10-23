"""Contract tests for flashcards MCP tool over Streamable HTTP (T3.10)."""

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
from sahayak.core.module import Deps, ModuleRegistry
from sahayak.main import create_app
from sahayak.modules.academics.service.flashcards import FlashcardService
from sahayak.modules.academics.tools.flashcards import set_flashcard_service
from tests.security.isolation import ISOLATION_REGISTRY, assert_user_isolation


@pytest.fixture(scope="module")
def contract_rsa_key() -> rsa.RSAPrivateKey:
    """RSA private key for signing test JWTs."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def make_test_token(
    key: rsa.RSAPrivateKey,
    *,
    sub: str,
    scope: str = "academics.write",
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
async def test_flashcards_mcp_contract_full_lifecycle(
    contract_rsa_key: rsa.RSAPrivateKey,
) -> None:
    """Full HTTP contract test for flashcards: add -> review_next -> grade -> list_due -> replay."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    # Configure JWT validator with mock JWKS
    jwk_dict = dict(json.loads(RSAAlgorithm.to_jwk(contract_rsa_key.public_key())))
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
    registry.load(("academics",))

    deps = Deps(session_factory=session_factory)
    app = create_app(registry=registry, deps=deps, jwt_validator=validator)

    # Connect flashcard service to the session factory
    service = FlashcardService(session_factory=session_factory)
    set_flashcard_service(service)

    test_id = uuid.uuid4().hex[:8]
    token = make_test_token(contract_rsa_key, sub=f"user-{test_id}")
    headers = {"Authorization": f"Bearer {token}"}
    asgi_transport = httpx.ASGITransport(app=app)

    try:
        async with app.router.lifespan_context(app):
            async with (
                httpx.AsyncClient(
                    transport=asgi_transport, base_url="http://testserver", headers=headers
                ) as http_client,
                streamable_http_client(
                    "http://testserver/mcp", http_client=cast(Any, http_client)
                ) as (read_stream, write_stream),
                ClientSession(read_stream, write_stream) as session,
            ):
                await session.initialize()

                # 1. Add card
                add_req_id = f"req-add-{test_id}"
                add_res = await session.call_tool(
                    "flashcards",
                    arguments={
                        "action": "add",
                        "front": "What is the capital of Australia?",
                        "back": "Canberra",
                        "deck": "Geography",
                        "request_id": add_req_id,
                    },
                )
                add_data = json.loads(getattr(add_res.content[0], "text", "{}"))
                assert add_data.get("ok") is True
                assert "Added flashcard to Geography" in add_data.get("spoken_summary", "")
                card = add_data.get("data", {}).get("card", {})
                card_id = card.get("card_id")
                assert card_id is not None
                assert card.get("front") == "What is the capital of Australia?"
                assert card.get("deck") == "Geography"

                # 2. Idempotent replay of same add
                add_replay_res = await session.call_tool(
                    "flashcards",
                    arguments={
                        "action": "add",
                        "front": "What is the capital of Australia?",
                        "back": "Canberra",
                        "deck": "Geography",
                        "request_id": add_req_id,
                    },
                )
                add_replay_data = json.loads(getattr(add_replay_res.content[0], "text", "{}"))
                assert add_replay_data.get("ok") is True
                assert add_replay_data.get("data", {}).get("card", {}).get("card_id") == card_id

                # 3. Review next due
                rev_res = await session.call_tool(
                    "flashcards",
                    arguments={"action": "review_next", "deck": "Geography"},
                )
                rev_data = json.loads(getattr(rev_res.content[0], "text", "{}"))
                assert rev_data.get("ok") is True
                assert "What is the capital of Australia?" in rev_data.get("spoken_summary", "")
                assert "show answer" in rev_data.get("spoken_summary", "")
                assert rev_data.get("data", {}).get("card", {}).get("card_id") == card_id

                # 4. Grade card as good
                grade_res = await session.call_tool(
                    "flashcards",
                    arguments={
                        "action": "grade",
                        "card_id": card_id,
                        "rating": "good",
                        "request_id": f"req-grade-{test_id}",
                    },
                )
                grade_data = json.loads(getattr(grade_res.content[0], "text", "{}"))
                assert grade_data.get("ok") is True
                assert "Card graded as good" in grade_data.get("spoken_summary", "")
                assert grade_data.get("data", {}).get("next_review_days") == 1
                assert grade_data.get("data", {}).get("card", {}).get("repetitions") == 1

                # 5. List due cards after grading (card scheduled 1 day in the future)
                list_res = await session.call_tool(
                    "flashcards",
                    arguments={"action": "list_due", "deck": "Geography"},
                )
                list_data = json.loads(getattr(list_res.content[0], "text", "{}"))
                assert list_data.get("ok") is True
                assert list_data.get("data", {}).get("total_due") == 0
                assert list_data.get("data", {}).get("cards") == []

                # 6. Review next after all cards graded
                rev_caught_up = await session.call_tool(
                    "flashcards",
                    arguments={"action": "review_next", "deck": "Geography"},
                )
                caught_up_data = json.loads(getattr(rev_caught_up.content[0], "text", "{}"))
                assert caught_up_data.get("ok") is True
                assert "all caught up" in caught_up_data.get("spoken_summary", "").lower()
                assert caught_up_data.get("data", {}).get("total_due") == 0

            # 7. Anonymous call rejected with auth_required
            async with (
                httpx.AsyncClient(
                    transport=asgi_transport, base_url="http://testserver"
                ) as anon_client,
                streamable_http_client(
                    "http://testserver/mcp", http_client=cast(Any, anon_client)
                ) as (ra, wa),
                ClientSession(ra, wa) as anon_session,
            ):
                await anon_session.initialize()
                anon_res = await anon_session.call_tool(
                    "flashcards", arguments={"action": "list_due"}
                )
                anon_data = json.loads(getattr(anon_res.content[0], "text", "{}"))
                assert anon_data.get("ok") is False
                assert anon_data.get("error_code") == "auth_required"

            # 8. Run user isolation regression check
            await assert_user_isolation(ISOLATION_REGISTRY["flashcards"], app, contract_rsa_key)

    finally:
        set_flashcard_service(None)
        await jwks_client.aclose()
        await engine.dispose()
