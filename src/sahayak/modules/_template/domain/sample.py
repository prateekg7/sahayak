"""Domain logic for the template module.

Domain models are pure business objects that never import from adapters,
frameworks, or I/O.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PingMessage:
    """Pure domain value object representing a ping payload."""

    message: str

    def echo(self) -> str:
        """Return the echoed text."""
        return f"echo: {self.message}"
