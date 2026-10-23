"""Abstract ports and result models for external data sources (T12.1)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Generic, Protocol, TypeVar

T = TypeVar("T", covariant=True)


@dataclass(frozen=True)
class DataSourceResult(Generic[T]):
    """Standard container for data retrieved from an external data source."""

    data: T
    source_id: str
    source_name: str
    license: str
    attribution: str
    fetched_at: datetime
    is_stale: bool = False
    cached_at: datetime | None = None

    @property
    def effective_timestamp(self) -> datetime:
        """Timestamp indicating when the data was originally produced or cached."""
        return self.cached_at or self.fetched_at


class DataSourcePort(Protocol, Generic[T]):
    """Protocol implemented by external data source adapters."""

    @property
    def source_id(self) -> str:
        """Stable unique identifier for the source (e.g., 'agmarknet', 'delhi_metro')."""
        ...

    @property
    def source_name(self) -> str:
        """Human-readable display name for the source."""
        ...

    @property
    def license(self) -> str:
        """License name or public data terms (e.g., 'ODbL 1.0', 'Government Open Data License')."""
        ...

    @property
    def attribution(self) -> str:
        """Required attribution text."""
        ...

    @property
    def default_ttl_seconds(self) -> int:
        """Default cache retention period in seconds."""
        ...
