"""Tests for the temporary container entry point."""

from __future__ import annotations

import signal
import sys

import pytest

from sahayak import container


def test_unknown_container_role_is_rejected() -> None:
    """Reject invalid roles rather than silently starting the wrong process."""
    assert container.run("unknown") == 2


def test_valid_container_role_stops_cleanly(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Stop the bootstrap process cleanly when it receives a termination signal."""
    handlers: dict[signal.Signals, object] = {}

    class StoppedEvent:
        def set(self) -> None:
            """Accept the stop request."""

        def wait(self) -> None:
            """Deliver the installed signal handler without blocking the test."""
            handler = handlers[signal.SIGTERM]
            assert callable(handler)
            handler(signal.SIGTERM, None)

    def register_handler(
        signal_number: signal.Signals,
        handler: object,
    ) -> None:
        """Capture handlers instead of mutating the test runner's signals."""
        handlers[signal_number] = handler

    monkeypatch.setattr(container, "Event", StoppedEvent)
    monkeypatch.setattr(signal, "signal", register_handler)

    assert container.run("app") == 0
    assert "sahayak app bootstrap is running" in capsys.readouterr().out


def test_main_requires_exactly_one_role_argument(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reject malformed command lines with a conventional status code."""
    monkeypatch.setattr(sys, "argv", ["container"])

    assert container.main() == 2


def test_worker_container_role_invokes_worker_main(monkeypatch: pytest.MonkeyPatch) -> None:
    """Delegate worker container execution to sahayak.worker.main."""
    from unittest.mock import MagicMock

    mock_main = MagicMock(return_value=0)
    monkeypatch.setattr("sahayak.worker.main", mock_main)

    assert container.run("worker") == 0
    mock_main.assert_called_once()
