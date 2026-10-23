"""Unit tests for government scheme declarative rules engine and domain logic (T12.4)."""

from __future__ import annotations

import pytest

from sahayak.modules.local_info.domain.schemes import (
    DISCLAIMER_TEXT,
    SchemeCriteria,
    SchemeDefinition,
    SchemeRepository,
    UserProfile,
    evaluate_scheme,
    format_check_spoken,
    format_explain_spoken,
    format_find_spoken,
)


@pytest.fixture
def sample_farmer_scheme() -> SchemeDefinition:
    return SchemeDefinition(
        id="pm_kisan",
        name="PM-Kisan Samman Nidhi",
        category="agriculture",
        beneficiary_desc="Small and marginal farmers",
        benefits_summary="6,000 rupees annual income support",
        official_portal_url="https://pmkisan.gov.in",
        last_verified_date="2026-10-24",
        criteria=SchemeCriteria(
            min_age=18,
            max_age=None,
            max_annual_income_inr=None,
            allowed_occupations=["farmer"],
            requires_landowner=True,
        ),
    )


@pytest.fixture
def sample_pension_scheme() -> SchemeDefinition:
    return SchemeDefinition(
        id="atal_pension",
        name="Atal Pension Yojana",
        category="financial_inclusion",
        beneficiary_desc="Citizens in unorganized sector",
        benefits_summary="Guaranteed monthly pension of 1,000 to 5,000 rupees after age 60",
        official_portal_url="https://www.npscra.nsdl.co.in",
        last_verified_date="2026-10-24",
        criteria=SchemeCriteria(
            min_age=18,
            max_age=40,
            max_annual_income_inr=250000,
            allowed_occupations=["any"],
        ),
    )


def test_rules_engine_eligible_farmer(sample_farmer_scheme: SchemeDefinition) -> None:
    profile = UserProfile(age=35, occupation="farmer", is_landowner=True)
    res = evaluate_scheme(sample_farmer_scheme, profile)
    assert res.status == "eligible"
    assert "criteria met" in res.reasons[0].lower()


def test_rules_engine_disqualified_non_landowner(sample_farmer_scheme: SchemeDefinition) -> None:
    profile = UserProfile(age=35, occupation="farmer", is_landowner=False)
    res = evaluate_scheme(sample_farmer_scheme, profile)
    assert res.status == "disqualified"
    assert "land ownership" in res.reasons[0].lower()


def test_rules_engine_disqualified_over_age(sample_pension_scheme: SchemeDefinition) -> None:
    profile = UserProfile(age=45, annual_income_inr=150000)
    res = evaluate_scheme(sample_pension_scheme, profile)
    assert res.status == "disqualified"
    assert "exceeds maximum age of 40" in res.reasons[0]


def test_rules_engine_disqualified_high_income(sample_pension_scheme: SchemeDefinition) -> None:
    profile = UserProfile(age=30, annual_income_inr=600000)
    res = evaluate_scheme(sample_pension_scheme, profile)
    assert res.status == "disqualified"
    assert "exceeds ceiling" in res.reasons[0]


def test_rules_engine_missing_info(sample_farmer_scheme: SchemeDefinition) -> None:
    # Farmer occupation provided, but landowner status unknown
    profile = UserProfile(age=30, occupation="farmer")
    res = evaluate_scheme(sample_farmer_scheme, profile)
    assert res.status == "missing_info"
    assert "is_landowner" in res.missing_fields


def test_scheme_repository_loading_and_lookup() -> None:
    repo = SchemeRepository()
    schemes = repo.all_schemes
    assert len(schemes) >= 10

    # Lookup by exact ID
    s_kisan = repo.find_by_name_or_id("pm_kisan")
    assert s_kisan is not None
    assert s_kisan.name == "PM-Kisan Samman Nidhi"

    # Lookup by name
    s_ayush = repo.find_by_name_or_id("Ayushman Bharat")
    assert s_ayush is not None
    assert s_ayush.id == "ayushman_bharat"

    # Unknown
    assert repo.find_by_name_or_id("Nonexistent Moon Scheme") is None


def test_format_find_spoken_includes_disclaimer_and_length_limit(
    sample_farmer_scheme: SchemeDefinition,
) -> None:
    profile = UserProfile(age=35, occupation="farmer", is_landowner=True)
    res = evaluate_scheme(sample_farmer_scheme, profile)
    spoken = format_find_spoken([res])
    assert len(spoken) <= 300
    assert "PM-Kisan Samman Nidhi" in spoken
    assert DISCLAIMER_TEXT in spoken
    assert "*" not in spoken


def test_format_explain_spoken(sample_farmer_scheme: SchemeDefinition) -> None:
    spoken = format_explain_spoken(sample_farmer_scheme)
    assert len(spoken) <= 300
    assert "pmkisan.gov.in" in spoken
    assert DISCLAIMER_TEXT in spoken


def test_format_check_spoken(sample_pension_scheme: SchemeDefinition) -> None:
    profile_ok = UserProfile(age=28, annual_income_inr=200000)
    res_ok = evaluate_scheme(sample_pension_scheme, profile_ok)
    spoken_ok = format_check_spoken(res_ok)
    assert len(spoken_ok) <= 300
    assert "appear eligible" in spoken_ok
    assert DISCLAIMER_TEXT in spoken_ok

    profile_disq = UserProfile(age=48, annual_income_inr=200000)
    res_disq = evaluate_scheme(sample_pension_scheme, profile_disq)
    spoken_disq = format_check_spoken(res_disq)
    assert len(spoken_disq) <= 300
    assert "do not meet the criteria" in spoken_disq
    assert DISCLAIMER_TEXT in spoken_disq


def test_validate_schemes_dataset_script() -> None:
    from scripts.validate_schemes import validate_schemes_dataset

    errors = validate_schemes_dataset()
    assert len(errors) == 0, f"Schemes dataset validation failed with errors: {errors}"
