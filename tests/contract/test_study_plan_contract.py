"""Contract tests for study_plan MCP tool over Streamable HTTP (T3.12)."""

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
from sahayak.modules.academics.service.plan import StudyPlanService
from sahayak.modules.academics.tools.study_plan import set_study_plan_service
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
async def test_study_plan_mcp_contract_full_lifecycle(
    contract_rsa_key: rsa.RSAPrivateKey,
) -> None:
    """Full HTTP contract test for study_plan lifecycle:

    create -> today -> mark done -> replan -> list -> replay.
    """
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

    service = StudyPlanService(session_factory=session_factory)
    set_study_plan_service(service)

    test_id = uuid.uuid4().hex[:8]
    token = make_test_token(contract_rsa_key, sub=f"user-plan-{test_id}")
    headers = {"Authorization": f"Bearer {token}"}
    asgi_transport = httpx.ASGITransport(app=app)

    try:
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=asgi_transport, base_url="http://testserver", headers=headers
            ) as http_client,
            streamable_http_client("http://testserver/mcp", http_client=cast(Any, http_client)) as (
                read_stream,
                write_stream,
            ),
            ClientSession(read_stream, write_stream) as session,
        ):
            await session.initialize()

            # 1. Create plan
            create_req_id = f"req-create-plan-{test_id}"
            create_res = await session.call_tool(
                "study_plan",
                arguments={
                    "action": "create",
                    "goal": "Biochemistry Exam",
                    "exam_date": "2026-11-20",
                    "topics": ["Proteins", "Enzymes", "Lipids"],
                    "hours_per_day": 1.5,
                    "request_id": create_req_id,
                },
            )
            create_data = json.loads(getattr(create_res.content[0], "text", "{}"))
            assert create_data.get("ok") is True, f"Create plan failed: {create_data}"
            plan_id = create_data.get("data", {}).get("plan_id")
            assert plan_id is not None
            assert "Biochemistry Exam" in create_data.get("spoken_summary", "")

            # 2. Fetch today's tasks
            today_res = await session.call_tool(
                "study_plan",
                arguments={"action": "today", "plan_id": plan_id},
            )
            today_data = json.loads(getattr(today_res.content[0], "text", "{}"))
            assert today_data.get("ok") is True
            tasks = today_data.get("data", {}).get("today_tasks", [])
            assert len(tasks) > 0
            first_task_id = tasks[0].get("task_id")
            assert first_task_id is not None

            # 3. Mark task done
            done_res = await session.call_tool(
                "study_plan",
                arguments={
                    "action": "update",
                    "task_id": first_task_id,
                    "mark_done": True,
                },
            )
            done_data = json.loads(getattr(done_res.content[0], "text", "{}"))
            assert done_data.get("ok") is True
            assert done_data.get("data", {}).get("updated_task", {}).get("done") is True

            # 4. Replan remaining days
            replan_res = await session.call_tool(
                "study_plan",
                arguments={
                    "action": "update",
                    "plan_id": plan_id,
                    "replan": True,
                    "hours_per_day": 2.0,
                },
            )
            replan_data = json.loads(getattr(replan_res.content[0], "text", "{}"))
            assert replan_data.get("ok") is True
            assert "replanned" in replan_data.get("spoken_summary", "")

            # 5. List study plans
            list_res = await session.call_tool(
                "study_plan",
                arguments={"action": "list"},
            )
            list_data = json.loads(getattr(list_res.content[0], "text", "{}"))
            assert list_data.get("ok") is True
            plans = list_data.get("data", {}).get("plans", [])
            assert any(p.get("plan_id") == plan_id for p in plans)

            # 6. Idempotent replay of create request
            replay_res = await session.call_tool(
                "study_plan",
                arguments={
                    "action": "create",
                    "goal": "Biochemistry Exam",
                    "exam_date": "2026-11-20",
                    "topics": ["Proteins", "Enzymes", "Lipids"],
                    "hours_per_day": 1.5,
                    "request_id": create_req_id,
                },
            )
            replay_data = json.loads(getattr(replay_res.content[0], "text", "{}"))
            assert replay_data.get("ok") is True
            assert replay_data.get("data", {}).get("plan_id") == plan_id

            # 7. Run user isolation regression check
            await assert_user_isolation(ISOLATION_REGISTRY["study_plan"], app, contract_rsa_key)

    finally:
        set_study_plan_service(None)
        await jwks_client.aclose()
        await engine.dispose()


@pytest.mark.asyncio
async def test_study_plan_mcp_contract_anonymous_rejected() -> None:
    """Anonymous callers cannot use study_plan tool."""
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
            res = await session.call_tool("study_plan", arguments={"action": "list"})
            data = json.loads(getattr(res.content[0], "text", "{}"))
            assert data.get("ok") is False
            assert data.get("error_code") == "auth_required"
    finally:
        await engine.dispose()
