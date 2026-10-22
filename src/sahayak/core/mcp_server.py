"""Stateless Streamable HTTP MCP server wiring.

Provides the FastMCP / MCPServer instance configured for stateless HTTP,
json_response=True, spec-compliant 405 on GET /mcp, and registration of
all enabled modules' tools through the ModuleRegistry.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Response
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette

from sahayak.core.config import Settings, get_settings
from sahayak.core.module import Deps, ModuleRegistry, get_registry

logger = logging.getLogger(__name__)

# Alias FastMCP to MCPServer for PRD §8/§9 compatibility
FastMCP = MCPServer


class MCPRoutingMiddleware:
    """ASGI middleware routing /mcp requests directly to the MCP Streamable HTTP app.

    Enforces GET /mcp returning 405 Method Not Allowed per MCP spec when
    server-initiated SSE streams are not used in stateless HTTP mode.
    """

    def __init__(self, app: Any, mcp_app: Starlette) -> None:
        self.app = app
        self.mcp_app = mcp_app

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Any,
        send: Any,
    ) -> None:
        """Intercept /mcp requests and forward to the MCP app or reject GET."""
        if scope["type"] == "http" and scope["path"] in ("/mcp", "/mcp/"):
            if scope["method"] == "GET":
                resp = Response(
                    content=(
                        "Method Not Allowed: server-initiated SSE streams "
                        "are disabled in stateless HTTP mode."
                    ),
                    status_code=405,
                    media_type="text/plain",
                )
                await resp(scope, receive, send)
                return
            if scope["method"] == "POST":
                normalized_scope = dict(scope)
                normalized_scope["path"] = "/mcp"
                await self.mcp_app(normalized_scope, receive, send)
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
        A Starlette application serving the /mcp endpoint in stateless mode.
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
        stateless_http=True,
        transport_security=transport_sec,
    )
    return app


def mount_mcp_server(
    fastapi_app: FastAPI,
    mcp_app: Starlette,
) -> None:
    """Mount the MCP Streamable HTTP sub-application into the FastAPI app.

    Args:
        fastapi_app: The parent FastAPI application.
        mcp_app: The Starlette MCP application.
    """
    fastapi_app.add_middleware(MCPRoutingMiddleware, mcp_app=mcp_app)
