"""Application service orchestrating template use cases."""

from __future__ import annotations

from sahayak.modules._template.domain.sample import PingMessage
from sahayak.modules._template.ports import PingRepositoryPort


class TemplateService:
    """Service handling template operations."""

    def __init__(self, repo: PingRepositoryPort) -> None:
        self._repo = repo

    async def process_ping(self, raw_message: str) -> str:
        """Process an inbound ping message and persist an audit entry.

        Args:
            raw_message: The text provided by the caller.

        Returns:
            The formatted echo response.
        """
        ping = PingMessage(message=raw_message)
        await self._repo.record_ping(raw_message)
        return ping.echo()
