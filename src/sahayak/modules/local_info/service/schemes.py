"""Service coordinating scheme discovery, eligibility checking, and explanations (T12.4)."""

from __future__ import annotations

from typing import Any

from sahayak.core.errors import InvalidInputError
from sahayak.modules.local_info.domain.schemes import (
    DISCLAIMER_TEXT,
    EligibilityResult,
    SchemeRepository,
    UserProfile,
    evaluate_scheme,
    format_check_spoken,
    format_explain_spoken,
    format_find_spoken,
)


class SchemeService:
    """Service providing government welfare scheme discovery and eligibility advice."""

    def __init__(self, repository: SchemeRepository | None = None) -> None:
        self._repo = repository or SchemeRepository()

    def _determine_next_clarification_question(
        self,
        missing_counts: dict[str, int],
        profile: UserProfile,
    ) -> str | None:
        """Pick the single highest-priority missing fact for voice conversational guidance."""
        if not profile.occupation and missing_counts.get("occupation", 0) > 0:
            return (
                "To find government schemes you may qualify for, "
                "what is your primary occupation, such as farmer, street vendor, or student?"
            )
        if profile.age is None and missing_counts.get("age", 0) > 0:
            return "Could you tell me your age to check age-specific welfare benefits?"
        if profile.annual_income_inr is None and missing_counts.get("annual_income_inr", 0) > 0:
            return (
                "What is your approximate annual household income in rupees "
                "to verify low-income scheme limits?"
            )
        if profile.is_landowner is None and missing_counts.get("is_landowner", 0) > 0:
            return "Do you own agricultural cultivable land?"
        return None

    async def find_schemes(self, profile: UserProfile) -> tuple[str, dict[str, Any]]:
        """Find matching schemes for a user profile, asking for one fact if missing."""
        all_schemes = self._repo.all_schemes

        # If profile has zero information provided, ask for primary occupation first
        if (
            profile.age is None
            and profile.annual_income_inr is None
            and profile.occupation is None
            and profile.state is None
            and profile.gender is None
            and profile.is_landowner is None
        ):
            spoken = (
                "To check which government welfare schemes you may qualify for, "
                "could you tell me your primary occupation, such as farmer, artisan, or student?"
            )
            initial_data: dict[str, Any] = {
                "schemes": [],
                "status": "needs_clarification",
                "missing_field": "occupation",
                "disclaimer": DISCLAIMER_TEXT,
            }
            return spoken, initial_data

        eligible: list[EligibilityResult] = []
        missing_counts: dict[str, int] = {}

        for scheme in all_schemes:
            res = evaluate_scheme(scheme, profile)
            if res.status == "eligible":
                eligible.append(res)
            elif res.status == "missing_info":
                for field_name in res.missing_fields:
                    missing_counts[field_name] = missing_counts.get(field_name, 0) + 1

        next_q: str | None = None
        if not eligible and missing_counts:
            next_q = self._determine_next_clarification_question(missing_counts, profile)

        spoken = format_find_spoken(eligible, next_question=next_q)

        data: dict[str, Any] = {
            "eligible_count": len(eligible),
            "schemes": [
                {
                    "id": e.scheme.id,
                    "name": e.scheme.name,
                    "category": e.scheme.category,
                    "benefits_summary": e.scheme.benefits_summary,
                    "official_portal_url": e.scheme.official_portal_url,
                    "reasons": e.reasons,
                }
                for e in eligible
            ],
            "disclaimer": DISCLAIMER_TEXT,
        }

        return spoken, data

    async def explain_scheme(self, scheme_query: str) -> tuple[str, dict[str, Any]]:
        """Explain benefits and application instructions for a specific welfare scheme."""
        scheme = self._repo.find_by_name_or_id(scheme_query)
        if not scheme:
            raise InvalidInputError(
                spoken=(
                    f"I could not find a government scheme matching '{scheme_query}'. "
                    "Try asking about PM-Kisan, Ayushman Bharat, or Mudra loans."
                ),
                detail=f"Scheme '{scheme_query}' not found in database.",
            )

        spoken = format_explain_spoken(scheme)

        data = {
            "id": scheme.id,
            "name": scheme.name,
            "category": scheme.category,
            "beneficiary_desc": scheme.beneficiary_desc,
            "benefits_summary": scheme.benefits_summary,
            "official_portal_url": scheme.official_portal_url,
            "last_verified_date": scheme.last_verified_date,
            "disclaimer": DISCLAIMER_TEXT,
        }

        return spoken, data

    async def check_eligibility(
        self,
        scheme_query: str,
        profile: UserProfile,
    ) -> tuple[str, dict[str, Any]]:
        """Check qualification criteria for a specific welfare scheme."""
        scheme = self._repo.find_by_name_or_id(scheme_query)
        if not scheme:
            raise InvalidInputError(
                spoken=f"I could not find a scheme matching '{scheme_query}'.",
                detail=f"Scheme '{scheme_query}' not found in database.",
            )

        result = evaluate_scheme(scheme, profile)
        spoken = format_check_spoken(result)

        data = {
            "id": scheme.id,
            "name": scheme.name,
            "status": result.status,
            "reasons": result.reasons,
            "missing_fields": result.missing_fields,
            "official_portal_url": scheme.official_portal_url,
            "disclaimer": DISCLAIMER_TEXT,
        }

        return spoken, data
