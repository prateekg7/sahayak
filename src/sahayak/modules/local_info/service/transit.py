"""Service coordinating transit resolution, departure fetching, and spoken responses (T12.2)."""

from __future__ import annotations

from typing import Any

from sahayak.modules.local_info.adapters.transit import TransitHttpDataSource
from sahayak.modules.local_info.domain.transit import (
    format_departures_spoken,
    format_line_status_spoken,
    resolve_station,
)


class TransitService:
    """Service providing transit departures and line status checks."""

    def __init__(self, data_source: TransitHttpDataSource | None = None) -> None:
        self._data_source = data_source or TransitHttpDataSource()

    async def get_next_departures(
        self,
        station_query: str,
        line_filter: str | None = None,
        destination_filter: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Resolve station and return upcoming departures with natural spoken summary."""
        station = resolve_station(station_query)
        result = await self._data_source.get_departures(station.code, station.name)

        departures = result.data
        if line_filter:
            departures = [d for d in departures if line_filter.lower() in d.line.lower()]
        if destination_filter:
            departures = [
                d for d in departures if destination_filter.lower() in d.destination.lower()
            ]

        spoken = format_departures_spoken(
            station.name,
            departures,
            is_fallback=result.is_stale and not departures,
            is_stale=result.is_stale,
        )

        data = {
            "station": station.name,
            "station_code": station.code,
            "lines": station.lines,
            "departures": [
                {
                    "line": d.line,
                    "destination": d.destination,
                    "platform": d.platform,
                    "eta_minutes": d.eta_minutes,
                    "scheduled_time": d.scheduled_time,
                    "status": d.status,
                }
                for d in departures
            ],
            "source": {
                "source_id": result.source_id,
                "source_name": result.source_name,
                "license": result.license,
                "attribution": result.attribution,
                "as_of": result.effective_timestamp.isoformat(),
                "is_stale": result.is_stale,
            },
        }

        return spoken, data

    async def get_line_status(
        self,
        line_filter: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Return operational line status and frequency alerts."""
        result = await self._data_source.get_line_statuses()
        lines = result.data

        if line_filter:
            filtered_lines = [item for item in lines if line_filter.lower() in item.line.lower()]
            if filtered_lines:
                lines = filtered_lines

        spoken = format_line_status_spoken(
            result.data,
            line_filter=line_filter,
            is_stale=result.is_stale,
        )

        data = {
            "lines": [
                {
                    "line": item.line,
                    "status": item.status,
                    "frequency_minutes": item.frequency_minutes,
                    "message": item.message,
                }
                for item in lines
            ],
            "source": {
                "source_id": result.source_id,
                "source_name": result.source_name,
                "license": result.license,
                "attribution": result.attribution,
                "as_of": result.effective_timestamp.isoformat(),
                "is_stale": result.is_stale,
            },
        }

        return spoken, data
