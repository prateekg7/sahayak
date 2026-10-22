"""Tests for the observability foundation: logging, metrics, tracing, and redaction (T0.12)."""

from __future__ import annotations

import pytest
from pydantic import SecretStr
from starlette.testclient import TestClient

from sahayak.core.config import Settings
from sahayak.core.observability.instrumentation import instrument_tool
from sahayak.core.observability.logging import configure_logging, get_logger
from sahayak.core.observability.metrics import (
    CACHE_HITS_TOTAL,
    CACHE_MISSES_TOTAL,
    TOOL_CALLS_TOTAL,
    render_metrics,
)
from sahayak.core.observability.redaction import (
    redact_text,
    redact_value,
    redaction_processor,
)
from sahayak.core.observability.tracing import get_tracer
from sahayak.core.request_id import set_request_id
from sahayak.main import create_app


def test_redaction_text_scrubs_bearer_and_email() -> None:
    """Bearer tokens, JWTs, and email addresses must be redacted from strings."""
    sample = "Call from user@example.com with Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.t-ID"
    scrubbed = redact_text(sample)
    assert "user@example.com" not in scrubbed
    assert "[REDACTED_EMAIL]" in scrubbed
    assert "Bearer [REDACTED]" in scrubbed
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in scrubbed


def test_redaction_processor_masks_sensitive_keys() -> None:
    """Sensitive keys (token, password, secret) in structlog dictionaries must be masked."""
    event_dict = {
        "event": "user_login",
        "email": "alice@example.com",
        "password": "super-secret-password",
        "nested": {"token": "12345", "public": "visible"},
    }
    processed = redaction_processor(None, "info", event_dict)
    assert processed["password"] == "[REDACTED]"
    assert processed["email"] == "[REDACTED_EMAIL]"
    assert processed["nested"]["token"] == "[REDACTED]"
    assert processed["nested"]["public"] == "visible"


def test_redact_value_handles_primitives_and_lists() -> None:
    """Non-string primitives and lists are handled correctly."""
    assert redact_value(123) == 123
    assert redact_value(None) is None
    scrubbed_list = redact_value(["user@example.com", 456])
    assert scrubbed_list == ["[REDACTED_EMAIL]", 456]


@pytest.mark.asyncio
async def test_instrument_tool_success_path() -> None:
    """Instrument tool records metrics, spans, and emits structured log."""
    set_request_id("req_obs_123")
    before_count = TOOL_CALLS_TOTAL.labels(
        tool="test_tool", module="test_mod", outcome="success"
    )._value.get()

    async with instrument_tool("test_tool", "test_mod"):
        pass

    after_count = TOOL_CALLS_TOTAL.labels(
        tool="test_tool", module="test_mod", outcome="success"
    )._value.get()
    assert after_count == before_count + 1


@pytest.mark.asyncio
async def test_instrument_tool_error_path() -> None:
    """Instrument tool captures exceptions and records error outcome."""
    set_request_id("req_obs_err")
    before_count = TOOL_CALLS_TOTAL.labels(
        tool="err_tool", module="test_mod", outcome="error"
    )._value.get()

    with pytest.raises(ValueError, match="simulated failure"):
        async with instrument_tool("err_tool", "test_mod"):
            raise ValueError("simulated failure")

    after_count = TOOL_CALLS_TOTAL.labels(
        tool="err_tool", module="test_mod", outcome="error"
    )._value.get()
    assert after_count == before_count + 1


def test_metrics_rendering() -> None:
    """render_metrics returns Prometheus exposition bytes containing registered metrics."""
    CACHE_HITS_TOTAL.labels(cache_name="test_cache").inc(5)
    CACHE_MISSES_TOTAL.labels(cache_name="test_cache").inc(2)

    data, content_type = render_metrics()
    text = data.decode("utf-8")
    assert "sahayak_cache_hits_total" in text
    assert "sahayak_tool_calls_total" in text
    assert "text/plain" in content_type


def test_metrics_endpoint_unauthenticated_when_token_configured() -> None:
    """GET /metrics returns 401 when metrics_token is set and no auth header is provided."""
    settings = Settings(
        metrics_token=SecretStr("supersecret123"),
        _env_file=None,  # type: ignore[call-arg]
    )
    app = create_app(settings=settings)
    with TestClient(app) as client:
        resp = client.get("/metrics")
        assert resp.status_code == 401

        # Providing valid token
        auth_resp = client.get(
            "/metrics",
            headers={"Authorization": "Bearer supersecret123"},
        )
        assert auth_resp.status_code == 200
        assert "sahayak_" in auth_resp.text

        # Providing valid X-Metrics-Token
        x_resp = client.get(
            "/metrics",
            headers={"X-Metrics-Token": "supersecret123"},
        )
        assert x_resp.status_code == 200


def test_metrics_endpoint_public_when_no_token() -> None:
    """GET /metrics returns 200 when no metrics_token is configured."""
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/metrics")
        assert resp.status_code == 200
        assert "sahayak_" in resp.text


def test_logging_configuration_and_tracer() -> None:
    """configure_logging and get_tracer execute cleanly."""
    configure_logging(json_output=True)
    logger = get_logger("test")
    assert logger is not None

    tracer = get_tracer("test")
    assert tracer is not None

    from sahayak.core.observability.logging import add_request_id

    set_request_id("req_log_test")
    d = add_request_id(None, "info", {})
    assert d["request_id"] == "req_log_test"

    configure_logging(json_output=False)
