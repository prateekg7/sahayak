"""Stable error types that map to voice-friendly MCP error codes.

Every domain or service error inherits from ``SahayakError`` and carries
a stable ``code`` used by the result envelope and spoken to the end user.
See PRD §9.4 for the error code table.
"""

from __future__ import annotations


class SahayakError(Exception):
    """Base for all application errors that reach the tool response layer.

    Attributes:
        code: Stable machine-readable code included in the error envelope.
        spoken: Short, actionable message safe for voice output.
        detail: Optional developer-facing detail logged but never sent to users.
    """

    code: str = "internal"

    def __init__(
        self,
        spoken: str = "Something went wrong on my side.",
        *,
        detail: str | None = None,
    ) -> None:
        super().__init__(spoken)
        self.spoken = spoken
        self.detail = detail


class InvalidInputError(SahayakError):
    """Schema or semantic validation failure."""

    code: str = "invalid_input"

    def __init__(
        self,
        spoken: str = "I didn't understand that input. Could you try again?",
        *,
        detail: str | None = None,
    ) -> None:
        super().__init__(spoken, detail=detail)


class NotFoundError(SahayakError):
    """Requested resource is unknown or expired."""

    code: str = "not_found"

    def __init__(
        self,
        spoken: str = "I can't find that. Want to start fresh?",
        *,
        detail: str | None = None,
    ) -> None:
        super().__init__(spoken, detail=detail)


class AuthRequiredError(SahayakError):
    """The tool requires a linked account."""

    code: str = "auth_required"

    def __init__(
        self,
        spoken: str = "Link your account in the Alexa app to use this feature.",
        *,
        detail: str | None = None,
    ) -> None:
        super().__init__(spoken, detail=detail)


class ForbiddenError(SahayakError):
    """The principal lacks the required scope."""

    code: str = "forbidden"

    def __init__(
        self,
        spoken: str = "You don't have permission for that action.",
        *,
        detail: str | None = None,
    ) -> None:
        super().__init__(spoken, detail=detail)


class RateLimitedError(SahayakError):
    """The caller has been throttled."""

    code: str = "rate_limited"

    def __init__(
        self,
        spoken: str = "Let's slow down for a moment and try again shortly.",
        *,
        detail: str | None = None,
    ) -> None:
        super().__init__(spoken, detail=detail)


class UpstreamUnavailableError(SahayakError):
    """An external dependency failed after retries and fallback."""

    code: str = "upstream_unavailable"

    def __init__(
        self,
        spoken: str = "I'm having trouble right now. Please try again soon.",
        *,
        detail: str | None = None,
    ) -> None:
        super().__init__(spoken, detail=detail)
