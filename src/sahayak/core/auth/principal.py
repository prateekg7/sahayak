"""Principal model, context tracking, and tool authorization decorators."""

from __future__ import annotations

import functools
import uuid
from collections.abc import Callable, Coroutine
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any, TypeVar, cast

from sahayak.core.envelope import fail
from sahayak.core.errors import AuthRequiredError, ForbiddenError

T = TypeVar("T")
ToolHandler = Callable[..., Coroutine[Any, Any, dict[str, Any]]]


@dataclass(frozen=True)
class Principal:
    """Identity context for the active invocation."""

    user_id: uuid.UUID | None = None
    scopes: frozenset[str] = frozenset()
    anonymous: bool = True
    issuer: str | None = None
    subject: str | None = None

    def has_scope(self, scope: str) -> bool:
        """Check whether the principal holds the requested authorization scope."""
        return scope in self.scopes


_ANONYMOUS_PRINCIPAL = Principal(user_id=None, scopes=frozenset(), anonymous=True)
_current_principal: ContextVar[Principal | None] = ContextVar("current_principal", default=None)


def get_current_principal() -> Principal:
    """Return the principal bound to the active execution context."""
    return _current_principal.get() or _ANONYMOUS_PRINCIPAL


def set_current_principal(principal: Principal) -> Token[Principal | None]:
    """Bind a principal to the active execution context."""
    return _current_principal.set(principal)


def reset_current_principal(token: Token[Principal | None]) -> None:
    """Reset the principal context variable to its previous state."""
    _current_principal.reset(token)


def requires(
    scope: str | None = None,
) -> Callable[[ToolHandler], ToolHandler]:
    """Enforce that the caller is authenticated and holds the required scope.

    If the principal is unauthenticated, returns an error envelope with
    error_code="auth_required".
    If authenticated but missing the required scope, returns an error
    envelope with error_code="forbidden".
    """

    def decorator(fn: ToolHandler) -> ToolHandler:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
            principal = get_current_principal()
            if principal.anonymous or principal.user_id is None:
                return fail(AuthRequiredError())
            if scope is not None and not principal.has_scope(scope):
                return fail(ForbiddenError())
            return await fn(*args, **kwargs)

        cast(Any, wrapper)._requires_scope = scope
        cast(Any, wrapper)._is_protected = True
        return wrapper

    return decorator


def allow_anonymous(fn: ToolHandler) -> ToolHandler:
    """Explicitly declare that a tool may be invoked without a linked account."""
    cast(Any, fn)._allow_anonymous = True
    return fn
