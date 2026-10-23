"""Unit tests for government scheme service (T12.4)."""

from __future__ import annotations

import pytest

from sahayak.core.errors import InvalidInputError
from sahayak.modules.local_info.domain.schemes import UserProfile
from sahayak.modules.local_info.service.schemes import SchemeService


@pytest.mark.asyncio
async def test_scheme_service_find_blank_profile_asks_one_question() -> None:
    service = SchemeService()
    spoken, data = await service.find_schemes(UserProfile())

    assert len(spoken) <= 300
    assert "primary occupation" in spoken
    assert data["status"] == "needs_clarification"
    assert data["missing_field"] == "occupation"


@pytest.mark.asyncio
async def test_scheme_service_find_with_occupation() -> None:
    service = SchemeService()
    # Farmer who owns land
    profile = UserProfile(age=35, occupation="farmer", is_landowner=True)
    spoken, data = await service.find_schemes(profile)

    assert len(spoken) <= 300
    assert "PM-Kisan" in spoken or "Kisan Credit Card" in spoken
    assert data["eligible_count"] >= 1
    assert "disclaimer" in data


@pytest.mark.asyncio
async def test_scheme_service_explain_scheme() -> None:
    service = SchemeService()
    spoken, data = await service.explain_scheme("ayushman bharat")

    assert len(spoken) <= 300
    assert "pmjay.gov.in" in spoken
    assert data["name"] == "Ayushman Bharat PM-JAY"
    assert "official_portal_url" in data


@pytest.mark.asyncio
async def test_scheme_service_explain_unknown_raises() -> None:
    service = SchemeService()
    with pytest.raises(InvalidInputError) as exc_info:
        await service.explain_scheme("Interstellar Hyperdrive Subsidy")
    assert "could not find a government scheme" in exc_info.value.spoken
    assert exc_info.value.code == "invalid_input"


@pytest.mark.asyncio
async def test_scheme_service_check_eligibility() -> None:
    service = SchemeService()
    profile = UserProfile(age=25, annual_income_inr=200000)
    spoken, data = await service.check_eligibility("atal pension", profile)

    assert len(spoken) <= 300
    assert "appear eligible" in spoken
    assert data["status"] == "eligible"
