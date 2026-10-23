"""Domain models, station dictionary, fuzzy resolver, and spoken formatters for transit (T12.2)."""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

from sahayak.core.errors import InvalidInputError


@dataclass(frozen=True)
class StationInfo:
    """Canonical transit station details."""

    code: str
    name: str
    lines: list[str]
    aliases: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DepartureInfo:
    """Single transit departure schedule or real-time status."""

    line: str
    destination: str
    platform: str
    eta_minutes: int
    scheduled_time: str
    status: str = "On Time"


@dataclass(frozen=True)
class LineStatusInfo:
    """Operational status and frequency for a transit line."""

    line: str
    status: str
    frequency_minutes: int
    message: str


# Canonical stations database with colloquial aliases and line mappings
CANONICAL_STATIONS: list[StationInfo] = [
    StationInfo(
        code="RC",
        name="Rajiv Chowk",
        lines=["Yellow", "Blue"],
        aliases=["cp", "connaught place", "rajiv chawk", "rc", "rajive chowk"],
    ),
    StationInfo(
        code="KG",
        name="Kashmere Gate",
        lines=["Red", "Yellow", "Violet"],
        aliases=["isbt", "kashmiri gate", "kashmir gate", "kg", "kashmeri gate"],
    ),
    StationInfo(
        code="NDLS",
        name="New Delhi",
        lines=["Yellow", "Airport Express"],
        aliases=["ndls", "new delhi railway station", "new delhi station", "pahar ganj"],
    ),
    StationInfo(
        code="HK",
        name="Hauz Khas",
        lines=["Yellow", "Magenta"],
        aliases=["hk", "hauzkhas", "iit", "iit delhi"],
    ),
    StationInfo(
        code="MCC",
        name="Millennium City Centre Gurugram",
        lines=["Yellow"],
        aliases=["huda", "huda city centre", "millennium city", "gurugram", "gurgaon"],
    ),
    StationInfo(
        code="IGI",
        name="IGI Airport",
        lines=["Airport Express"],
        aliases=["airport", "t3", "terminal 3", "delhi airport", "aerocity", "terminal 1"],
    ),
    StationInfo(
        code="CC",
        name="Chandni Chowk",
        lines=["Yellow"],
        aliases=["cc", "old delhi", "chandani chowk", "chandni chawk", "red fort"],
    ),
    StationInfo(
        code="CS",
        name="Central Secretariat",
        lines=["Yellow", "Violet"],
        aliases=["cs", "krishi bhawan", "secretariat", "udyog bhawan"],
    ),
    StationInfo(
        code="BG",
        name="Botanical Garden",
        lines=["Blue", "Magenta"],
        aliases=["bg", "botanical", "noida botanical"],
    ),
    StationInfo(
        code="NCC",
        name="Noida City Centre",
        lines=["Blue"],
        aliases=["ncc", "noida sector 32", "noida centre", "noida"],
    ),
    StationInfo(
        code="VSH",
        name="Vaishali",
        lines=["Blue"],
        aliases=["vaishali", "ghaziabad"],
    ),
    StationInfo(
        code="AV",
        name="Anand Vihar ISBT",
        lines=["Blue", "Pink"],
        aliases=["anand vihar", "av", "anand vihar isbt", "anand vihar railway station"],
    ),
    StationInfo(
        code="SB",
        name="Samaypur Badli",
        lines=["Yellow"],
        aliases=["samaypur badli", "badli", "samaypur"],
    ),
    StationInfo(
        code="RIT",
        name="Rithala",
        lines=["Red"],
        aliases=["rithala", "rohini"],
    ),
    StationInfo(
        code="DIL",
        name="Dilshad Garden",
        lines=["Red"],
        aliases=["dilshad garden", "dilshad"],
    ),
]

_CANONICAL_LOOKUP: dict[str, StationInfo] = {}
for station in CANONICAL_STATIONS:
    _CANONICAL_LOOKUP[station.code.lower()] = station
    _CANONICAL_LOOKUP[station.name.lower()] = station
    for alias in station.aliases:
        _CANONICAL_LOOKUP[alias.lower()] = station


def _clean_query(text: str) -> str:
    """Normalize user voice input for station matching."""
    cleaned = re.sub(r"[^\w\s]", "", text.lower())
    # Strip common filler tokens
    tokens = [t for t in cleaned.split() if t not in {"metro", "station", "stop", "train", "halt"}]
    return " ".join(tokens).strip()


def resolve_station(query: str) -> StationInfo:
    """Resolve a spoken station name, abbreviation, or alias to a canonical station.

    Supports exact alias match, code match, token matching, and Levenshtein fuzzy matching.
    Raises InvalidInputError if no close match is found.
    """
    raw_query = query.strip()
    if not raw_query:
        raise InvalidInputError(
            spoken=(
                "Please specify a station name, such as Rajiv Chowk, Hauz Khas, or Kashmere Gate."
            ),
            detail="Station query is empty.",
        )

    cleaned = _clean_query(raw_query)
    lookup_key = cleaned if cleaned else raw_query.lower()

    # 1. Exact lookup in dictionary
    if lookup_key in _CANONICAL_LOOKUP:
        return _CANONICAL_LOOKUP[lookup_key]

    # 2. Check prefix / substring matches
    for key, station in _CANONICAL_LOOKUP.items():
        if lookup_key == key or (len(lookup_key) >= 3 and lookup_key in key):
            return station

    # 3. Fuzzy Levenshtein match across all station names and aliases
    all_candidates = list(_CANONICAL_LOOKUP.keys())
    matches = difflib.get_close_matches(lookup_key, all_candidates, n=1, cutoff=0.68)
    if matches:
        return _CANONICAL_LOOKUP[matches[0]]

    # 4. No satisfactory match
    raise InvalidInputError(
        spoken=(
            f"I could not find a metro or train station matching '{raw_query}'. "
            "Try naming a major station like Rajiv Chowk, Kashmere Gate, or Hauz Khas."
        ),
        detail=f"Station '{raw_query}' (clean '{cleaned}') not resolved to canonical station.",
    )


def format_departures_spoken(
    station_name: str,
    departures: list[DepartureInfo],
    *,
    is_fallback: bool = False,
    is_stale: bool = False,
) -> str:
    """Format departures into a natural voice summary strictly under 300 characters."""
    if is_fallback or not departures:
        res = (
            f"Live tracking is temporarily unavailable for {station_name}. "
            "Trains run with regular frequency every 3 to 5 minutes during daytime hours."
        )
        return res[:300]

    parts: list[str] = []
    for dep in departures[:2]:  # Speak up to 2 next departures to keep voice response concise
        unit = "minute" if dep.eta_minutes == 1 else "minutes"
        eta_str = f"in {dep.eta_minutes} {unit}" if dep.eta_minutes > 0 else "now"
        parts.append(
            f"{dep.line} Line toward {dep.destination} {eta_str} on platform {dep.platform}"
        )

    joined = " and ".join(parts)
    spoken = f"Next departures from {station_name}: {joined}."
    if is_stale:
        spoken += " Schedule may be delayed."

    # Enforce 300 chars limit
    if len(spoken) > 300:
        spoken = spoken[:297] + "..."
    return spoken


def format_line_status_spoken(
    lines: list[LineStatusInfo],
    *,
    line_filter: str | None = None,
    is_stale: bool = False,
) -> str:
    """Format transit line statuses into a spoken summary under 300 characters."""
    if not lines:
        return "All major metro and suburban lines are operating normally today."

    if line_filter:
        matching = [item for item in lines if line_filter.lower() in item.line.lower()]
        if matching:
            target = matching[0]
            spoken = (
                f"{target.line} Line is operating with {target.status.lower()} service. "
                f"Trains run every {target.frequency_minutes} minutes. {target.message}"
            )
            if is_stale:
                spoken += " Status updated recently."
            return spoken.strip()[:300]

    # Overall summary
    delayed = [item for item in lines if item.status.lower() not in {"normal", "on time"}]
    if not delayed:
        spoken = "All major metro lines are operating with normal service and regular frequencies."
    else:
        names = ", ".join(item.line for item in delayed[:2])
        spoken = (
            f"Most lines are normal, but {names} Line is experiencing minor delays. "
            "Please allow extra travel time."
        )

    if is_stale:
        spoken += " Note: Status was cached earlier."

    return spoken[:300]
