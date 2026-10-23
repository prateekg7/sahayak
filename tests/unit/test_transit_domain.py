"""Unit tests for transit domain models, fuzzy station resolver, and spoken formatters (T12.2)."""

from __future__ import annotations

import pytest

from sahayak.core.errors import InvalidInputError
from sahayak.modules.local_info.domain.transit import (
    DepartureInfo,
    LineStatusInfo,
    format_departures_spoken,
    format_line_status_spoken,
    resolve_station,
)


def test_station_resolution_exact_and_codes() -> None:
    assert resolve_station("Rajiv Chowk").code == "RC"
    assert resolve_station("rc").code == "RC"
    assert resolve_station("NDLS").code == "NDLS"
    assert resolve_station("New Delhi").code == "NDLS"
    assert resolve_station("Hauz Khas").code == "HK"
    assert resolve_station("Kashmere Gate").code == "KG"


def test_station_resolution_colloquial_aliases() -> None:
    # "cp" -> Rajiv Chowk
    assert resolve_station("cp").code == "RC"
    assert resolve_station("Connaught Place").code == "RC"

    # "isbt" / "kashmiri gate" -> Kashmere Gate
    assert resolve_station("isbt").code == "KG"
    assert resolve_station("kashmir gate").code == "KG"

    # "huda" / "gurgaon" -> Millennium City Centre
    assert resolve_station("huda").code == "MCC"
    assert resolve_station("gurgaon").code == "MCC"

    # "airport" / "t3" -> IGI Airport
    assert resolve_station("airport").code == "IGI"
    assert resolve_station("t3").code == "IGI"
    assert resolve_station("terminal 3").code == "IGI"

    # "anand vihar" -> Anand Vihar ISBT
    assert resolve_station("anand vihar").code == "AV"


def test_station_resolution_with_filler_words() -> None:
    # Users saying "rajiv chowk metro station" or "hauz khas stop"
    assert resolve_station("rajiv chowk metro station").code == "RC"
    assert resolve_station("hauz khas station").code == "HK"
    assert resolve_station("kashmere gate train stop").code == "KG"


def test_station_resolution_fuzzy_misspellings() -> None:
    # Common speech-to-text typos
    assert resolve_station("rajv chowk").code == "RC"
    assert resolve_station("kashmr gate").code == "KG"
    assert resolve_station("chandani chawk").code == "CC"
    assert resolve_station("botanik garden").code == "BG"


def test_station_resolution_unknown_raises_invalid_input() -> None:
    with pytest.raises(InvalidInputError) as exc_info:
        resolve_station("Atlantis Deep Station")
    assert "could not find a metro or train station" in exc_info.value.spoken
    assert exc_info.value.code == "invalid_input"

    with pytest.raises(InvalidInputError):
        resolve_station("   ")


def test_format_departures_spoken_within_length_budget() -> None:
    deps = [
        DepartureInfo(
            line="Yellow",
            destination="Samaypur Badli",
            platform="1",
            eta_minutes=3,
            scheduled_time="10:15",
            status="On Time",
        ),
        DepartureInfo(
            line="Blue",
            destination="Noida Electronic City",
            platform="3",
            eta_minutes=5,
            scheduled_time="10:17",
            status="On Time",
        ),
    ]

    spoken = format_departures_spoken("Rajiv Chowk", deps)
    assert len(spoken) <= 300
    assert "Rajiv Chowk" in spoken
    assert "Yellow Line toward Samaypur Badli in 3 minutes on platform 1" in spoken
    assert "Blue Line toward Noida Electronic City in 5 minutes on platform 3" in spoken
    # No markdown
    assert "*" not in spoken
    assert "`" not in spoken
    assert "#" not in spoken


def test_format_departures_fallback_spoken() -> None:
    spoken = format_departures_spoken("Hauz Khas", [], is_fallback=True)
    assert len(spoken) <= 300
    assert "Live tracking is temporarily unavailable for Hauz Khas" in spoken
    assert "regular frequency" in spoken


def test_format_line_status_spoken() -> None:
    lines = [
        LineStatusInfo(
            line="Yellow",
            status="Normal",
            frequency_minutes=4,
            message="Operating normally.",
        ),
        LineStatusInfo(
            line="Blue",
            status="Minor Delays",
            frequency_minutes=8,
            message="Signal testing near Yamuna Bank.",
        ),
    ]

    # Overall summary with delayed line
    spoken = format_line_status_spoken(lines)
    assert len(spoken) <= 300
    assert "Blue Line is experiencing minor delays" in spoken

    # Line-specific summary
    spoken_yellow = format_line_status_spoken(lines, line_filter="yellow")
    assert len(spoken_yellow) <= 300
    assert "Yellow Line is operating with normal service" in spoken_yellow
    assert "every 4 minutes" in spoken_yellow
