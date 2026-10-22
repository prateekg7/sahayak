"""Contract test exercising initialize -> tools/list -> tools/call over HTTP (T0.11)."""

from __future__ import annotations

import json
from typing import Any, cast

import httpx
import pytest
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

from sahayak.core.module import ModuleRegistry
from sahayak.main import create_app


@pytest.mark.asyncio
async def test_mcp_http_contract_e2e() -> None:
    """Full HTTP contract: initialize, list tools, and invoke ping_echo."""
    registry = ModuleRegistry()
    registry.load(("_template",))
    app = create_app(registry=registry)

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
        # 1. Initialize
        init_res = await session.initialize()
        assert init_res.protocol_version == "2025-11-25"
        assert init_res.server_info.name == "sahayak"

        # 2. List tools
        tools_res = await session.list_tools()
        names = [t.name for t in tools_res.tools]
        assert "ping_echo" in names

        # 3. Call tool
        call_res = await session.call_tool("ping_echo", arguments={"message": "contract-test"})
        assert not call_res.is_error
        assert len(call_res.content) > 0

        first_block = call_res.content[0]
        text_val = getattr(first_block, "text", "")
        payload = json.loads(text_val)

        # Standard result envelope checks (§9.3)
        assert payload["ok"] is True
        assert "spoken_summary" in payload
        assert "data" in payload
        assert "next_actions" in payload
        assert "meta" in payload
        assert payload["meta"]["module"] == "_template"
        assert payload["data"]["echo"] == "echo: contract-test"
