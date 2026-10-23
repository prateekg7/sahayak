"""User isolation testing harness and auto-discovery verification (T1.9)."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any, cast

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.server.mcpserver import MCPServer


@dataclass(frozen=True)
class ToolIsolationSpec:
    """Security and user isolation specification for an MCP tool."""

    name: str
    allows_anonymous: bool
    required_scopes: list[str] = field(default_factory=list)
    sample_args: dict[str, Any] = field(default_factory=dict)
    custom_isolation_check: (
        Callable[[ClientSession, ClientSession], Coroutine[Any, Any, None]] | None
    ) = None


ISOLATION_REGISTRY: dict[str, ToolIsolationSpec] = {}


def register_isolation_spec(spec: ToolIsolationSpec) -> None:
    """Register isolation test coverage for a specific tool."""
    ISOLATION_REGISTRY[spec.name] = spec


def get_untested_tools(server: MCPServer) -> list[str]:
    """Return all tool names registered on the server that lack an isolation spec."""
    tools = server._tool_manager.list_tools()
    registered_names = set(ISOLATION_REGISTRY.keys())
    return [t.name for t in tools if t.name not in registered_names]


def make_test_jwt(
    key: rsa.RSAPrivateKey,
    *,
    sub: str,
    scope: str = "",
    expires_in: int = 3600,
) -> str:
    """Helper to mint a valid test token."""
    now = int(time.time())
    payload = {
        "sub": sub,
        "iss": "https://auth.example.com",
        "aud": "sahayak-api",
        "exp": now + expires_in,
        "iat": now,
        "nbf": now,
        "scope": scope,
    }
    return jwt.encode(payload, key, algorithm="RS256", headers={"kid": "sec-test-key"})


async def assert_user_isolation(
    spec: ToolIsolationSpec,
    app: Any,
    rsa_key: rsa.RSAPrivateKey,
) -> None:
    """Assert that a tool strictly enforces anonymous/authenticated isolation."""
    asgi_transport = httpx.ASGITransport(app=app)

    # 1. Test anonymous access
    async with (
        httpx.AsyncClient(transport=asgi_transport, base_url="http://testserver") as client,
        streamable_http_client("http://testserver/mcp", http_client=cast(Any, client)) as (r, w),
        ClientSession(r, w) as session,
    ):
        await session.initialize()
        res = await session.call_tool(spec.name, arguments=spec.sample_args)
        data = json.loads(getattr(res.content[0], "text", "{}"))

        if spec.allows_anonymous:
            assert data.get("ok") is True, f"Anonymous tool {spec.name} failed: {data}"
        else:
            assert data.get("ok") is False, (
                f"Protected tool {spec.name} should fail anonymously: {data}"
            )
            assert data.get("error_code") == "auth_required"

    # 2. If tool requires scopes, test missing scope rejection
    if not spec.allows_anonymous and spec.required_scopes:
        token_wrong_scope = make_test_jwt(rsa_key, sub="user-wrong-scope", scope="unrelated.scope")
        headers = {"Authorization": f"Bearer {token_wrong_scope}"}

        async with (
            httpx.AsyncClient(
                transport=asgi_transport, base_url="http://testserver", headers=headers
            ) as client,
            streamable_http_client("http://testserver/mcp", http_client=cast(Any, client)) as (
                r,
                w,
            ),
            ClientSession(r, w) as session,
        ):
            await session.initialize()
            res = await session.call_tool(spec.name, arguments=spec.sample_args)
            data = json.loads(getattr(res.content[0], "text", "{}"))
            assert data.get("ok") is False
            assert data.get("error_code") == "forbidden"

    # 3. Test cross-user isolation when authenticated
    if not spec.allows_anonymous or spec.custom_isolation_check is not None:
        token_user_a = make_test_jwt(
            rsa_key, sub="user-a", scope=" ".join(spec.required_scopes or ["academics.read"])
        )
        token_user_b = make_test_jwt(
            rsa_key, sub="user-b", scope=" ".join(spec.required_scopes or ["academics.read"])
        )

        headers_a = {"Authorization": f"Bearer {token_user_a}"}
        headers_b = {"Authorization": f"Bearer {token_user_b}"}

        async with (
            httpx.AsyncClient(
                transport=asgi_transport, base_url="http://testserver", headers=headers_a
            ) as client_a,
            httpx.AsyncClient(
                transport=asgi_transport, base_url="http://testserver", headers=headers_b
            ) as client_b,
            streamable_http_client("http://testserver/mcp", http_client=cast(Any, client_a)) as (
                ra,
                wa,
            ),
            streamable_http_client("http://testserver/mcp", http_client=cast(Any, client_b)) as (
                rb,
                wb,
            ),
            ClientSession(ra, wa) as session_a,
            ClientSession(rb, wb) as session_b,
        ):
            await session_a.initialize()
            await session_b.initialize()

            # Execute standard call under User A
            res_a = await session_a.call_tool(spec.name, arguments=spec.sample_args)
            data_a = json.loads(getattr(res_a.content[0], "text", "{}"))
            assert data_a.get("ok") is True, f"User A failed to call {spec.name}: {data_a}"

            # Execute standard call under User B
            res_b = await session_b.call_tool(spec.name, arguments=spec.sample_args)
            data_b = json.loads(getattr(res_b.content[0], "text", "{}"))
            assert data_b.get("ok") is True, f"User B failed to call {spec.name}: {data_b}"

            # If custom isolation check provided, run it
            if spec.custom_isolation_check is not None:
                await spec.custom_isolation_check(session_a, session_b)


# Register initial built-in tool isolation specifications
register_isolation_spec(
    ToolIsolationSpec(
        name="ping_echo",
        allows_anonymous=True,
        sample_args={"message": "hello security"},
    )
)

register_isolation_spec(
    ToolIsolationSpec(
        name="quiz_start",
        allows_anonymous=True,
        sample_args={"topic": "General Science", "num_questions": 3},
    )
)
