"""Contract tests for topic_brief MCP tool over Streamable HTTP (T3.14)."""

from __future__ import annotations

import json
from typing import Any, cast

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.config import get_settings
from sahayak.core.module import Deps, ModuleRegistry
from sahayak.main import create_app
from sahayak.modules.academics.service.brief import TopicBriefService
from sahayak.modules.academics.tools.brief import set_brief_service
from sahayak.shared.content.wikipedia import GroundingResult, WikipediaClient
from tests.security.isolation import ISOLATION_REGISTRY, assert_user_isolation


class ContractMockWikipediaClient(WikipediaClient):
    """Deterministic Wikipedia client for contract testing."""

    async def get_grounding(
        self,
        topic: str,
        *,
        language: str = "en",
        max_chars: int = 2000,
        timeout: float = 5.0,
    ) -> GroundingResult | None:
        return GroundingResult(
            title="General Science",
            raw_extract=(
                "General science is an academic discipline covering broad fundamentals of "
                "physics, chemistry, biology, and earth science. It provides students with "
                "core scientific literacy."
            ),
            sanitized_text=(
                "General science is an academic discipline covering broad fundamentals of "
                "physics, chemistry, biology, and earth science. It provides students with "
                "core scientific literacy."
            ),
            wrapped_prompt_text="<grounded_source_data>General science...</grounded_source_data>",
            url="https://en.wikipedia.org/wiki/General_Science",
        )


@pytest.fixture(scope="module")
def contract_rsa_key() -> rsa.RSAPrivateKey:
    """RSA private key for signing test JWTs."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.mark.asyncio
async def test_topic_brief_mcp_contract_lifecycle(
    contract_rsa_key: rsa.RSAPrivateKey,
) -> None:
    """Contract test for topic_brief over Streamable HTTP:

    1. Anonymous invocation succeeds with standard envelope.
    2. Sources are present and well-formed.
    3. Medium length option works.
    4. Invalid input returns error envelope.
    5. User isolation specification passes.
    """
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    registry = ModuleRegistry()
    registry.load(("academics",))
    deps = Deps(session_factory=session_factory)
    app = create_app(registry=registry, deps=deps)

    service = TopicBriefService(wikipedia=ContractMockWikipediaClient())
    set_brief_service(service)

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

            # 1. Anonymous call for short brief
            res_short = await session.call_tool(
                "topic_brief",
                arguments={"topic": "General Science", "length": "short"},
            )
            data_short = json.loads(getattr(res_short.content[0], "text", "{}"))
            assert data_short.get("ok") is True
            assert "General science is an academic discipline" in data_short.get(
                "spoken_summary", ""
            )
            assert len(data_short.get("spoken_summary", "")) <= 300
            sources = data_short.get("data", {}).get("sources", [])
            assert len(sources) == 1
            assert sources[0].get("title") == "General Science"
            assert "wikipedia.org" in sources[0].get("url", "")

            # 2. Medium brief call
            res_med = await session.call_tool(
                "topic_brief",
                arguments={"topic": "General Science", "length": "medium"},
            )
            data_med = json.loads(getattr(res_med.content[0], "text", "{}"))
            assert data_med.get("ok") is True
            assert data_med.get("data", {}).get("length") == "medium"

            # 3. Invalid length returns invalid_input
            res_bad = await session.call_tool(
                "topic_brief",
                arguments={"topic": "General Science", "length": "mega_long"},
            )
            data_bad = json.loads(getattr(res_bad.content[0], "text", "{}"))
            assert data_bad.get("ok") is False
            assert data_bad.get("error_code") == "invalid_input"

            # 4. Auto-isolation check
            await assert_user_isolation(ISOLATION_REGISTRY["topic_brief"], app, contract_rsa_key)
    finally:
        set_brief_service(None)
        await engine.dispose()
