"""Tests for the stateless Streamable HTTP MCP server wiring (T0.10)."""

from __future__ import annotations

import json
from typing import Any, cast

import httpx
import pytest
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from starlette.testclient import TestClient

from sahayak.core.config import Settings
from sahayak.core.mcp_server import create_mcp_app, create_mcp_server
from sahayak.core.module import ModuleRegistry
from sahayak.main import create_app


def test_get_mcp_returns_405_method_not_allowed() -> None:
    """GET /mcp must return 405 Method Not Allowed when SSE streams are disabled."""
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/mcp")
        assert resp.status_code == 405
        assert "Method Not Allowed" in resp.text
        assert "server-initiated SSE streams are disabled" in resp.text


@pytest.mark.asyncio
async def test_mcp_sdk_client_protocol_negotiation_and_tools() -> None:
    """SDK client connects over streamable HTTP, negotiates 2025-11-25, and calls ping_echo."""
    registry = ModuleRegistry()
    registry.load(("_template",))
    app = create_app(registry=registry)

    # Lifespan context initializes the streamable HTTP task group
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as http_client,
        streamable_http_client("http://testserver/mcp", http_client=cast(Any, http_client)) as (
            read_stream,
            write_stream,
        ),
        ClientSession(read_stream, write_stream) as session,
    ):
        init_res = await session.initialize()
        assert init_res.protocol_version == "2025-11-25"

        tools_res = await session.list_tools()
        tool_names = [t.name for t in tools_res.tools]
        assert "ping_echo" in tool_names

        # Verify description adheres to the format
        ping_tool = next(t for t in tools_res.tools if t.name == "ping_echo")
        assert ping_tool.description is not None
        assert "connectivity" in ping_tool.description.lower()

        call_res = await session.call_tool("ping_echo", arguments={"message": "hello world"})
        assert call_res.is_error is False or call_res.is_error is None
        assert len(call_res.content) > 0
        first_content = call_res.content[0]
        text_val = getattr(first_content, "text", "")
        assert "Pong. echo: hello world" in text_val

        data = json.loads(text_val)
        assert data["ok"] is True
        assert data["spoken_summary"] == "Pong. echo: hello world"
        assert data["data"]["echo"] == "echo: hello world"


@pytest.mark.asyncio
async def test_round_robin_across_two_stateless_replicas() -> None:
    """Two independent app replicas behind round-robin both answer correctly.

    Because the server is completely stateless (stateless_http=True),
    consecutive JSON-RPC messages routed to alternating replicas succeed.
    """
    reg1 = ModuleRegistry()
    reg1.load(("_template",))
    app1 = create_app(registry=reg1)

    reg2 = ModuleRegistry()
    reg2.load(("_template",))
    app2 = create_app(registry=reg2)

    apps = [app1, app2]
    call_index = 0

    class RoundRobinTransport(httpx.AsyncBaseTransport):
        """Alternates between app1 and app2 on each incoming HTTP request."""

        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            nonlocal call_index
            target_app = apps[call_index % 2]
            call_index += 1
            transport = httpx.ASGITransport(app=target_app)
            return await transport.handle_async_request(request)

    async with (
        app1.router.lifespan_context(app1),
        app2.router.lifespan_context(app2),
        httpx.AsyncClient(
            transport=RoundRobinTransport(), base_url="http://testserver"
        ) as http_client,
        streamable_http_client("http://testserver/mcp", http_client=cast(Any, http_client)) as (
            read_stream,
            write_stream,
        ),
        ClientSession(read_stream, write_stream) as session,
    ):
        init_res = await session.initialize()
        assert init_res.protocol_version == "2025-11-25"

        tools_res = await session.list_tools()
        assert any(t.name == "ping_echo" for t in tools_res.tools)

        call_res = await session.call_tool("ping_echo", arguments={"message": "roundrobin"})
        first_content = call_res.content[0]
        text_val = getattr(first_content, "text", "")
        assert "Pong. echo: roundrobin" in text_val

        data = json.loads(text_val)
        assert data["ok"] is True
        assert data["data"]["echo"] == "echo: roundrobin"


def test_create_mcp_app_with_allowed_origins() -> None:
    """Configuring allowed_origins enables DNS-rebinding protection."""
    settings = Settings(
        allowed_origins=("https://alexa.example.com",),  # type: ignore[arg-type]
        _env_file=None,  # type: ignore[call-arg]
    )
    registry = ModuleRegistry()
    registry.load(("_template",))
    server = create_mcp_server(settings=settings, registry=registry)
    app = create_mcp_app(server, settings=settings)
    assert app is not None
