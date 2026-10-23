"""Auto-discovery user isolation security tests for all registered tools (T1.9)."""

from __future__ import annotations

import json
import uuid

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from sahayak.core.auth.jwt import JWTValidator
from sahayak.core.config import get_settings
from sahayak.core.mcp_server import create_mcp_server
from sahayak.core.module import ModuleRegistry
from sahayak.main import create_app
from tests.security.isolation import (
    ISOLATION_REGISTRY,
    assert_user_isolation,
    get_untested_tools,
)


@pytest.fixture(scope="module")
def sec_rsa_key() -> rsa.RSAPrivateKey:
    """Generate RSA key for security regression tests."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def test_every_registered_tool_has_isolation_specification() -> None:
    """Auto-discovery gate: fails CI if any registered tool lacks isolation coverage."""
    settings = get_settings()
    registry = ModuleRegistry()
    registry.load(("_template", "academics", "productivity", "finance", "health", "career", "home"))
    server = create_mcp_server(settings=settings, registry=registry)

    untested = get_untested_tools(server)
    if untested:
        pytest.fail(
            f"The following tools lack user isolation test coverage: {untested}. "
            "Every MCP tool must register an isolation specification in "
            "tests/security/isolation.py."
        )


@pytest.mark.asyncio
async def test_auto_isolation_suite_passes_all_registered_tools(
    sec_rsa_key: rsa.RSAPrivateKey,
) -> None:
    """Run assert_user_isolation across all registered tool specifications."""
    jwk_dict = dict(json.loads(RSAAlgorithm.to_jwk(sec_rsa_key.public_key())))
    jwk_dict["kid"] = "sec-test-key"
    jwks = {"keys": [jwk_dict]}

    settings = get_settings()
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from sahayak.core.db.session import UnitOfWork
    from sahayak.core.module import Deps
    from sahayak.modules.academics.adapters.question_bank import SQLAlchemyQuestionBank
    from sahayak.modules.academics.models import DifficultyLevel, Question

    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
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
                    content_hash=f"gen_sci_{uuid.uuid4().hex[:12]}",
                    prompt_version="v1",
                    model="test-model",
                )
                for i in range(3)
            ]
            await bank.insert_questions(seeded)
            await uow.session.commit()

        transport_mock = httpx.MockTransport(lambda _: httpx.Response(200, json=jwks))
        async with httpx.AsyncClient(transport=transport_mock) as http_client:
            validator = JWTValidator(
                issuer="https://auth.example.com",
                audience="sahayak-api",
                jwks_url="https://auth.example.com/.well-known/jwks.json",
                http_client=http_client,
            )

            registry = ModuleRegistry()
            registry.load(
                ("_template", "academics", "productivity", "finance", "health", "career", "home")
            )
            deps = Deps(session_factory=session_factory)

            app = create_app(registry=registry, jwt_validator=validator, deps=deps)

            async with app.router.lifespan_context(app):
                for spec in ISOLATION_REGISTRY.values():
                    await assert_user_isolation(spec, app=app, rsa_key=sec_rsa_key)
    finally:
        await engine.dispose()
