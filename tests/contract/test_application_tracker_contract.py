"""Contract tests for application_tracker MCP tool over Streamable HTTP (T8.2)."""

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
from sahayak.modules.career.service.applications import ApplicationService
from sahayak.modules.career.tools.application_tracker import set_application_service
from sahayak.shared.users.models import User


@pytest.fixture(scope="module")
def app_contract_rsa_key() -> rsa.RSAPrivateKey:
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
async def test_application_tracker_contract_full_lifecycle(
    app_contract_rsa_key: rsa.RSAPrivateKey,
) -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    jwk_dict = dict(json.loads(RSAAlgorithm.to_jwk(app_contract_rsa_key.public_key())))
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

    app_service = ApplicationService(session_factory=session_factory)
    set_application_service(app_service)

    user_a = uuid.uuid4()
    async with UnitOfWork(session_factory) as uow:
        uow.session.add(User(id=user_a))
        await uow.session.commit()

    token_a = make_test_token(app_contract_rsa_key, sub=str(user_a))
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
                    "application_tracker", arguments={"action": "list"}
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

                # Add application
                res_add = await session_auth.call_tool(
                    "application_tracker",
                    arguments={
                        "action": "add",
                        "company": "Netflix",
                        "role": "Distributed Systems Engineer",
                        "status": "applied",
                        "follow_up_at": "in 3 days",
                    },
                )
                data_add = json.loads(getattr(res_add.content[0], "text", "{}"))
                assert data_add.get("ok") is True
                app_id = data_add.get("data", {}).get("application_id")
                assert app_id is not None
                assert len(data_add.get("spoken_summary", "")) <= 300

                # Update status
                res_upd = await session_auth.call_tool(
                    "application_tracker",
                    arguments={
                        "action": "update_status",
                        "application_id": app_id,
                        "status": "interviewing",
                    },
                )
                data_upd = json.loads(getattr(res_upd.content[0], "text", "{}"))
                assert data_upd.get("ok") is True
                assert data_upd.get("data", {}).get("status") == "interviewing"

                # List applications
                res_list = await session_auth.call_tool(
                    "application_tracker",
                    arguments={"action": "list"},
                )
                data_list = json.loads(getattr(res_list.content[0], "text", "{}"))
                assert data_list.get("ok") is True
                apps = data_list.get("data", {}).get("applications", [])
                assert len(apps) >= 1
                assert apps[0]["id"] == app_id

                # List due followups
                res_due = await session_auth.call_tool(
                    "application_tracker",
                    arguments={"action": "due_followups"},
                )
                data_due = json.loads(getattr(res_due.content[0], "text", "{}"))
                assert data_due.get("ok") is True
                due_apps = data_due.get("data", {}).get("due_followups", [])
                assert len(due_apps) >= 1
                assert due_apps[0]["company"] == "Netflix"

                # Delete application
                res_del = await session_auth.call_tool(
                    "application_tracker",
                    arguments={"action": "delete", "application_id": app_id},
                )
                data_del = json.loads(getattr(res_del.content[0], "text", "{}"))
                assert data_del.get("ok") is True
                assert data_del.get("data", {}).get("deleted") is True

                # Validation error on missing company
                res_err = await session_auth.call_tool(
                    "application_tracker",
                    arguments={"action": "add", "role": "Frontend Engineer"},
                )
                data_err = json.loads(getattr(res_err.content[0], "text", "{}"))
                assert data_err.get("ok") is False
                assert data_err.get("error_code") == "invalid_input"
    finally:
        await engine.dispose()
