"""Redaction processor and string sanitization for sensitive values.

Redacts authentication tokens, bearer headers, email addresses, and
sensitive fields before they reach log sinks or traces (PRD §24.4).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, MutableMapping
from typing import Any

# Regex patterns for sensitive data
_BEARER_PATTERN = re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE)
_EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
_JWT_PATTERN = re.compile(r"ey[A-Za-z0-9_-]{10,}\.[A-Za-z0-9._-]{10,}")

_SENSITIVE_KEY_NAMES = frozenset(
    {
        "token",
        "access_token",
        "refresh_token",
        "secret",
        "password",
        "authorization",
        "api_key",
        "apikey",
        "private_key",
    }
)


def redact_text(text: str) -> str:
    """Mask sensitive patterns (Bearer tokens, emails, JWTs) within a string."""
    text = _BEARER_PATTERN.sub("Bearer [REDACTED]", text)
    text = _JWT_PATTERN.sub("[REDACTED_JWT]", text)
    return _EMAIL_PATTERN.sub("[REDACTED_EMAIL]", text)


def redact_value(value: Any) -> Any:
    """Recursively scrub sensitive content from values, dictionaries, or lists."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        return {
            k: (
                "[REDACTED]"
                if isinstance(k, str) and k.lower() in _SENSITIVE_KEY_NAMES
                else redact_value(v)
            )
            for k, v in value.items()
        }
    if isinstance(value, list | tuple):
        return [redact_value(item) for item in value]
    return value


def redaction_processor(
    _logger: Any,
    _method_name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """Structlog processor that masks secrets and PII in event dicts."""
    for key in list(event_dict.keys()):
        if isinstance(key, str) and key.lower() in _SENSITIVE_KEY_NAMES:
            event_dict[key] = "[REDACTED]"
        else:
            event_dict[key] = redact_value(event_dict[key])
    return event_dict
