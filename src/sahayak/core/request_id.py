"""Request-correlation ID helpers shared by HTTP boundaries."""

from __future__ import annotations

from contextvars import ContextVar, Token

from ulid import ULID

REQUEST_ID_HEADER = "X-Request-ID"
_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def new_request_id() -> str:
    """Create an opaque, sortable correlation identifier."""
    return str(ULID())


def get_request_id() -> str | None:
    """Return the request ID bound to the current async context, if any."""
    return _request_id.get()


def set_request_id(request_id: str) -> Token[str | None]:
    """Bind a request ID to the current async context.

    Args:
        request_id: The already validated request identifier.

    Returns:
        A token that restores the prior context when reset.
    """
    return _request_id.set(request_id)


def reset_request_id(token: Token[str | None]) -> None:
    """Restore the request-ID context to the state before ``set_request_id``."""
    _request_id.reset(token)
