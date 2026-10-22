"""Log and PII redaction security tests (T1.9)."""

from __future__ import annotations

import json
from typing import Any

import jwt

from sahayak.core.observability.redaction import (
    redact_text,
    redact_value,
    redaction_processor,
)


def test_redact_bearer_tokens_and_jwts() -> None:
    """Authorization Bearer headers and raw JWTs are sanitized."""
    # Generate token dynamically to avoid committing literal secrets
    raw_jwt = jwt.encode({"sub": "test"}, key="test-secret", algorithm="HS256")
    sample = f"Calling provider with Authorization: Bearer secret-token-123 and token {raw_jwt}"

    sanitized = redact_text(sample)
    assert "secret-token-123" not in sanitized
    assert "[REDACTED]" in sanitized or "[REDACTED_JWT]" in sanitized


def test_redact_email_addresses() -> None:
    """User email addresses are sanitized to protect PII."""
    sample = "User person@example.com logged in successfully from test@corp.domain.org"
    sanitized = redact_text(sample)

    assert "person@example.com" not in sanitized
    assert "test@corp.domain.org" not in sanitized
    assert "[REDACTED_EMAIL]" in sanitized


def test_redact_sensitive_dictionary_keys() -> None:
    """Dictionaries containing secret key names have their values scrubbed."""
    payload: dict[str, Any] = {
        "user_id": "u-123",
        "access_token": "secret_access_value",
        "refresh_token": "secret_refresh_value",
        "password": "super_secret_value",
        "apiKey": "val_12345",
        "nested": {
            "secret": "top_secret_info",
            "safe_field": "public_data",
        },
    }

    sanitized = redact_value(payload)
    assert sanitized["user_id"] == "u-123"
    assert sanitized["access_token"] == "[REDACTED]"
    assert sanitized["refresh_token"] == "[REDACTED]"
    assert sanitized["password"] == "[REDACTED]"
    assert sanitized["apiKey"] == "[REDACTED]"
    assert sanitized["nested"]["secret"] == "[REDACTED]"
    assert sanitized["nested"]["safe_field"] == "public_data"


def test_structlog_redaction_processor() -> None:
    """Structlog event dicts are filtered by redaction_processor."""
    sample_jwt = jwt.encode({"user": "test"}, key="key", algorithm="HS256")
    event_dict: dict[str, Any] = {
        "event": "login_attempt",
        "email": "user@example.com",
        "authorization": f"Bearer {sample_jwt}",
        "safe_count": 42,
    }

    processed = redaction_processor(None, "info", event_dict)

    # Check serialization
    dumped = json.dumps(processed)
    assert "user@example.com" not in dumped
    assert "[REDACTED" in dumped
    assert processed["safe_count"] == 42
