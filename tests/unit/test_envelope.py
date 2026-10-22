"""Tests for the result envelope and error model."""

from __future__ import annotations

import json

import pytest

from sahayak.core.envelope import fail, lint_spoken, ok
from sahayak.core.errors import (
    AuthRequiredError,
    ForbiddenError,
    InvalidInputError,
    NotFoundError,
    RateLimitedError,
    SahayakError,
    UpstreamUnavailableError,
)


class TestErrorHierarchy:
    """Every error subclass carries its documented code and spoken message."""

    @pytest.mark.parametrize(
        ("cls", "code"),
        [
            (SahayakError, "internal"),
            (InvalidInputError, "invalid_input"),
            (NotFoundError, "not_found"),
            (AuthRequiredError, "auth_required"),
            (ForbiddenError, "forbidden"),
            (RateLimitedError, "rate_limited"),
            (UpstreamUnavailableError, "upstream_unavailable"),
        ],
    )
    def test_error_codes_are_stable(
        self,
        cls: type[SahayakError],
        code: str,
    ) -> None:
        assert cls.code == code

    def test_custom_spoken_and_detail(self) -> None:
        error = InvalidInputError("Tell me a topic.", detail="empty topic field")
        assert error.spoken == "Tell me a topic."
        assert error.detail == "empty topic field"
        assert str(error) == "Tell me a topic."


class TestOkEnvelope:
    """The ``ok`` helper produces the PRD §9.3 shape."""

    def test_minimal_ok_response(self) -> None:
        result = ok("It worked.")
        assert result["ok"] is True
        assert result["spoken_summary"] == "It worked."
        assert result["data"] == {}
        assert result["next_actions"] == []
        assert "request_id" in result["meta"]

    def test_ok_with_data_and_actions(self) -> None:
        result = ok(
            "Question 1 of 5.",
            data={"quiz_id": "abc"},
            next_actions=["answer the question"],
            module="academics",
            version="1.0.0",
        )
        assert result["data"] == {"quiz_id": "abc"}
        assert result["next_actions"] == ["answer the question"]
        assert result["meta"]["module"] == "academics"
        assert result["meta"]["version"] == "1.0.0"

    def test_spoken_summary_strips_markdown_and_urls(self) -> None:
        result = ok("Check **this** at https://example.com now!")
        assert "**" not in result["spoken_summary"]
        assert "https://" not in result["spoken_summary"]

    def test_spoken_summary_truncation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from sahayak.core import config, envelope

        settings = config.Settings(spoken_summary_max_chars=20)
        monkeypatch.setattr(envelope, "get_settings", lambda: settings)
        result = ok("A" * 50)
        assert len(result["spoken_summary"]) == 20
        assert result["spoken_summary"].endswith("\u2026")

    def test_response_size_enforcement(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from sahayak.core import config, envelope

        settings = config.Settings(max_response_bytes=200)
        monkeypatch.setattr(envelope, "get_settings", lambda: settings)
        result = ok("short", data={"big": "X" * 500})
        serialized = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
        assert len(serialized.encode()) <= 200
        assert result["data"] == {"_truncated": True}
        assert result["meta"]["truncated"] is True


class TestFailEnvelope:
    """The ``fail`` helper produces a stable error envelope."""

    def test_fail_envelope_shape(self) -> None:
        error = NotFoundError("Quiz not found.")
        result = fail(error, module="academics")
        assert result["ok"] is False
        assert result["error_code"] == "not_found"
        assert result["spoken_summary"] == "Quiz not found."
        assert result["meta"]["module"] == "academics"

    def test_fail_does_not_leak_detail(self) -> None:
        error = SahayakError("Oops.", detail="SQL error: relation missing")
        result = fail(error)
        serialized = json.dumps(result)
        assert "SQL error" not in serialized
        assert "relation missing" not in serialized


class TestSpokenLinter:
    """The lint helper catches voice-unsafe text."""

    def test_clean_spoken_has_no_problems(self) -> None:
        assert lint_spoken("Question 1 of 5. Which gas do plants absorb?") == []

    def test_markdown_is_flagged(self) -> None:
        problems = lint_spoken("Check **this**.")
        assert any("markdown" in p for p in problems)

    def test_url_is_flagged(self) -> None:
        problems = lint_spoken("Visit https://example.com.")
        assert any("URL" in p or "markdown" in p for p in problems)
