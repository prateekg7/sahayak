"""Streamable HTTP MCP server wiring for Alexa+ and standard MCP clients.

Provides the FastMCP / MCPServer instance configured for Streamable HTTP,
CORS preflight handling for web inspectors, spec-compliant 405 on GET /mcp
when in stateless mode, and tool payload envelope transformation ensuring
both structuredContent and content blocks are returned.
"""

from __future__ import annotations

import functools
import inspect
import json
import logging
from collections.abc import Callable, Sequence
from typing import Any

from fastapi import FastAPI, Response
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, TextContent
from starlette.applications import Starlette

from sahayak.core.config import Settings, get_settings
from sahayak.core.module import Deps, ModuleRegistry, get_registry

logger = logging.getLogger(__name__)

# Alias FastMCP to MCPServer for PRD §8/§9 compatibility
FastMCP = MCPServer


def wrap_tool_for_alexa(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap tool functions to return standard CallToolResult with structuredContent.

    Ensures both Alexa+ requirement (top-level structuredContent and optional
    _meta.ui) and standard MCP unstructured text blocks are populated.
    """

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        if inspect.iscoroutinefunction(fn):
            res = await fn(*args, **kwargs)
        else:
            res = fn(*args, **kwargs)

        if isinstance(res, dict):
            content_text = json.dumps(res, ensure_ascii=False)
            ui_meta = res.get("meta", {}).get("ui")
            meta_dict = {"ui": ui_meta} if ui_meta else None
            return CallToolResult(
                content=[TextContent(type="text", text=content_text)],
                structured_content=res,
                is_error=not res.get("ok", True),
                _meta=meta_dict,
            )
        return res

    wrapper.__annotations__ = getattr(fn, "__annotations__", {})
    return wrapper


class MCPRoutingMiddleware:
    """ASGI middleware routing /mcp requests directly to the MCP Streamable HTTP app.

    Enforces CORS preflight handling (OPTIONS /mcp), GET /mcp 405 Method Not Allowed
    when server-initiated SSE streams are disabled in stateless HTTP mode, and
    exposes required response headers (mcp-session-id, content-type).
    """

    def __init__(
        self,
        app: Any,
        mcp_app: Starlette,
        stateless_http: bool = True,
        allowed_origins: Sequence[str] = ("*",),
    ) -> None:
        self.app = app
        self.mcp_app = mcp_app
        self.stateless_http = stateless_http
        self.allowed_origins = set(allowed_origins) if allowed_origins else {"*"}

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Any,
        send: Any,
    ) -> None:
        """Intercept /mcp requests and forward to the MCP app or handle CORS/GET."""
        if scope["type"] == "http" and scope["path"] in ("/mcp", "/mcp/"):
            headers_dict = dict(scope.get("headers", []))
            origin_bytes = headers_dict.get(b"origin")
            origin = origin_bytes.decode("latin1") if origin_bytes else "*"
            allow_origin = (
                origin
                if ("*" in self.allowed_origins or origin in self.allowed_origins)
                else (next(iter(self.allowed_origins)) if self.allowed_origins else "*")
            )

            if scope["method"] == "OPTIONS":
                resp = Response(
                    status_code=204,
                    headers={
                        "Access-Control-Allow-Origin": allow_origin,
                        "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
                        "Access-Control-Allow-Headers": (
                            "Content-Type, Authorization, mcp-session-id, "
                            "mcp-protocol-version, last-event-id, accept, x-request-id"
                        ),
                        "Access-Control-Expose-Headers": (
                            "mcp-session-id, content-type, x-request-id"
                        ),
                        "Access-Control-Max-Age": "86400",
                    },
                )
                await resp(scope, receive, send)
                return

            if scope["method"] == "GET" and self.stateless_http:
                resp = Response(
                    content=(
                        "Method Not Allowed: server-initiated SSE streams "
                        "are disabled in stateless HTTP mode."
                    ),
                    status_code=405,
                    media_type="text/plain",
                    headers={
                        "Access-Control-Allow-Origin": allow_origin,
                        "Access-Control-Expose-Headers": (
                            "mcp-session-id, content-type, x-request-id"
                        ),
                    },
                )
                await resp(scope, receive, send)
                return

            if scope["method"] in ("GET", "POST", "DELETE"):
                normalized_scope = dict(scope)
                normalized_scope["path"] = "/mcp"

                async def send_with_cors(message: Any) -> None:
                    if message["type"] == "http.response.start":
                        headers = list(message.get("headers", []))
                        headers.append(
                            (b"access-control-allow-origin", allow_origin.encode("latin1"))
                        )
                        headers.append(
                            (
                                b"access-control-expose-headers",
                                b"mcp-session-id, content-type, x-request-id",
                            )
                        )
                        message = dict(message)
                        message["headers"] = headers
                    await send(message)

                await self.mcp_app(normalized_scope, receive, send_with_cors)
                return

        await self.app(scope, receive, send)


def create_mcp_server(
    settings: Settings | None = None,
    deps: Deps | None = None,
    registry: ModuleRegistry | None = None,
) -> MCPServer:
    """Create and configure the MCP server instance.

    Args:
        settings: Application settings.
        deps: Dependency container passed to registering modules.
        registry: Module registry instance. If None, uses process-wide singleton.

    Returns:
        Configured MCPServer ready to register tools.
    """
    app_settings = settings or get_settings()
    server = MCPServer(app_settings.app_name.lower())

    orig_add_tool = server.add_tool

    def alexa_add_tool(fn: Any, **kwargs: Any) -> None:
        wrapped = wrap_tool_for_alexa(fn)
        orig_add_tool(wrapped, **kwargs)

    server.add_tool = alexa_add_tool  # type: ignore[assignment,method-assign]

    mod_registry = registry or get_registry()
    injected_deps = deps or Deps()

    mod_registry.register_all_tools(server, injected_deps)
    logger.info(
        "configured MCP server with %d modules loaded",
        len(mod_registry.modules),
    )
    return server


def create_mcp_app(
    server: MCPServer,
    settings: Settings | None = None,
) -> Starlette:
    """Create the Streamable HTTP Starlette sub-application for MCP.

    Args:
        server: The MCPServer instance.
        settings: Application settings.

    Returns:
        A Starlette application serving the /mcp endpoint.
    """
    app_settings = settings or get_settings()

    # Allowed hosts and origins for DNS-rebinding protection per MCP spec
    allowed_hosts = ["*"]
    allowed_origins = (
        [str(o) for o in app_settings.allowed_origins] if app_settings.allowed_origins else ["*"]
    )

    transport_sec = TransportSecuritySettings(
        enable_dns_rebinding_protection=bool(app_settings.allowed_origins),
        allowed_hosts=allowed_hosts,
        allowed_origins=allowed_origins,
    )

    app: Starlette = server.streamable_http_app(
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=app_settings.mcp_stateless_http,
        transport_security=transport_sec,
    )
    return app


def mount_mcp_server(
    fastapi_app: FastAPI,
    mcp_app: Starlette,
    settings: Settings | None = None,
) -> None:
    """Mount the MCP Streamable HTTP sub-application into the FastAPI app.

    Args:
        fastapi_app: The parent FastAPI application.
        mcp_app: The Starlette MCP application.
        settings: Application settings.
    """
    app_settings = settings or get_settings()
    allowed_origins = (
        [str(o) for o in app_settings.allowed_origins] if app_settings.allowed_origins else ["*"]
    )
    fastapi_app.add_middleware(
        MCPRoutingMiddleware,
        mcp_app=mcp_app,
        stateless_http=app_settings.mcp_stateless_http,
        allowed_origins=allowed_origins,
    )
