"""ASGI middleware for extracting bearer tokens and binding the active Principal."""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any

from fastapi import Response

from sahayak.core.auth.jwt import JWTValidationError, JWTValidator
from sahayak.core.auth.principal import (
    Principal,
    reset_current_principal,
    set_current_principal,
)

if TYPE_CHECKING:
    from sahayak.shared.users.service import UserService

logger = logging.getLogger(__name__)


class AuthMiddleware:
    """Extracts bearer tokens from Authorization header and sets the active Principal.

    If an invalid or expired token is presented, returns HTTP 401 without
    WWW-Authenticate per ADR 0003. If no token is presented, binds an
    anonymous Principal so that public and unlinked tools can execute.
    """

    def __init__(
        self,
        app: Any,
        validator: JWTValidator | None = None,
        user_service: UserService | None = None,
    ) -> None:
        self.app = app
        self.validator = validator
        self.user_service = user_service

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Any,
        send: Any,
    ) -> None:
        """Process HTTP requests, resolving authentication before dispatch."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        auth_bytes = headers.get(b"authorization")
        principal = Principal(user_id=None, scopes=frozenset(), anonymous=True)

        if auth_bytes:
            auth_str = auth_bytes.decode("latin1").strip()
            if auth_str.lower().startswith("bearer "):
                token_val = auth_str[7:].strip()
                if self.validator is not None:
                    try:
                        claims = await self.validator.validate_token(token_val)
                        if self.user_service is not None:
                            user = await self.user_service.get_or_create_by_identity(
                                issuer=claims.issuer,
                                subject=claims.subject,
                            )
                            user_id = user.id
                        else:
                            user_id = uuid.uuid5(
                                uuid.NAMESPACE_URL,
                                f"{claims.issuer}:{claims.subject}",
                            )

                        principal = Principal(
                            user_id=user_id,
                            scopes=frozenset(claims.scopes),
                            anonymous=False,
                            issuer=claims.issuer,
                            subject=claims.subject,
                        )
                    except JWTValidationError as exc:
                        logger.warning("invalid bearer token presented: %s", exc)
                        # Return 401 without WWW-Authenticate header per ADR 0003
                        resp = Response(
                            content="Unauthorized: Invalid or expired token",
                            status_code=401,
                            media_type="text/plain",
                        )
                        await resp(scope, receive, send)
                        return

        token = set_current_principal(principal)
        try:
            await self.app(scope, receive, send)
        finally:
            reset_current_principal(token)
