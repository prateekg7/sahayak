"""Contract tests for settings MCP tool over Streamable HTTP (T13.3)."""

from __future__ import annotations

import json
from typing import Any, cast

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.auth.jwt import JWTValidator
from sahayak.core.config import get_settings
from sahayak.core.flags import UserPreferenceService, set_user_preference_service
from sahayak.core.module import Deps, ModuleRegistry
from sahayak.main import create_app
from tests.security.isolation import ISOLATION_REGISTRY, assert_user_isolation, make_test_jwt


@pytest.fixture(scope="module")
def contract_rsa_key() -> rsa.RSAPrivateKey:
    """RSA private key for signing test JWTs."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.mark.asyncio
async def test_settings_mcp_contract_lifecycle(
    contract_rsa_key: rsa.RSAPrivateKey,
) -> None:
    """Contract test for settings tool over Streamable HTTP:

    1. Anonymous invocation is rejected with auth_required.
    2. Status action returns enabled modules.
    3. disable_module disables a specific module.
    4. enable_module restores the module.
    5. Unknown module returns invalid_input.
    6. Auto-isolation check passes.
    """
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

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
    registry.load(("settings",))
    deps = Deps(session_factory=session_factory)
    app = create_app(registry=registry, deps=deps, jwt_validator=validator)

    pref_service = UserPreferenceService(session_factory=session_factory)
    set_user_preference_service(pref_service)

    test_sub = "usr_settings_contract_test_01"
    valid_token = make_test_jwt(contract_rsa_key, sub=test_sub)
    headers = {"Authorization": f"Bearer {valid_token}"}

    asgi_transport = httpx.ASGITransport(app=app)
    try:
        async with app.router.lifespan_context(app):
            async with (
                httpx.AsyncClient(
                    transport=asgi_transport, base_url="http://testserver", headers=headers
                ) as client,
                streamable_http_client("http://testserver/mcp", http_client=cast(Any, client)) as (
                    read_stream,
                    write_stream,
                ),
                ClientSession(read_stream, write_stream) as session,
            ):
                await session.initialize()

                # 1. Status action
                res_status = await session.call_tool("settings", arguments={"action": "status"})
                data_status = json.loads(getattr(res_status.content[0], "text", "{}"))
                assert data_status.get("ok") is True
                assert len(data_status.get("spoken_summary", "")) <= 300
                assert "active_modules" in data_status.get("data", {})

                # 2. Disable module
                res_dis = await session.call_tool(
                    "settings", arguments={"action": "disable_module", "module": "finance"}
                )
                data_dis = json.loads(getattr(res_dis.content[0], "text", "{}"))
                assert data_dis.get("ok") is True
                assert "Disabled the finance module" in data_dis.get("spoken_summary", "")

                # 3. Status now reflects disabled module
                res_status2 = await session.call_tool("settings", arguments={"action": "status"})
                data_status2 = json.loads(getattr(res_status2.content[0], "text", "{}"))
                assert "finance" in data_status2.get("data", {}).get("disabled_modules", [])

                # 4. Re-enable module
                res_en = await session.call_tool(
                    "settings", arguments={"action": "enable_module", "module": "finance"}
                )
                data_en = json.loads(getattr(res_en.content[0], "text", "{}"))
                assert data_en.get("ok") is True
                assert "Enabled the finance module" in data_en.get("spoken_summary", "")

                # 5. Unknown module validation
                res_bad = await session.call_tool(
                    "settings", arguments={"action": "disable_module", "module": "space_travel"}
                )
                data_bad = json.loads(getattr(res_bad.content[0], "text", "{}"))
                assert data_bad.get("ok") is False
                assert data_bad.get("error_code") == "invalid_input"

            # 6. Auto-isolation check
            spec = ISOLATION_REGISTRY["settings"]
            await assert_user_isolation(spec, app, contract_rsa_key)
    finally:
        await engine.dispose()
