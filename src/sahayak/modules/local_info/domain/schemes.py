"""Declarative rules engine, scheme definitions, and voice conversation formatters (T12.4)."""

from __future__ import annotations

import difflib
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

DISCLAIMER_TEXT = "This is informational guidance. Please verify details at the official portal."


@dataclass(frozen=True)
class SchemeCriteria:
    """Declarative criteria evaluated as pure deterministic code."""

    min_age: int | None = None
    max_age: int | None = None
    max_annual_income_inr: int | None = None
    allowed_occupations: list[str] = field(default_factory=lambda: ["any"])
    allowed_genders: list[str] = field(default_factory=lambda: ["all"])
    allowed_states: list[str] = field(default_factory=lambda: ["all"])
    requires_landowner: bool | None = None


@dataclass(frozen=True)
class SchemeDefinition:
    """Curated national or state welfare scheme."""

    id: str
    name: str
    category: str
    beneficiary_desc: str
    benefits_summary: str
    official_portal_url: str
    last_verified_date: str
    criteria: SchemeCriteria


@dataclass(frozen=True)
class UserProfile:
    """User profile attributes used for scheme eligibility assessment."""

    age: int | None = None
    annual_income_inr: int | None = None
    occupation: str | None = None
    state: str | None = None
    gender: str | None = None
    is_landowner: bool | None = None


@dataclass(frozen=True)
class EligibilityResult:
    """Result of evaluating a user profile against a scheme's criteria."""

    scheme: SchemeDefinition
    status: str  # "eligible", "disqualified", "missing_info"
    reasons: list[str]
    missing_fields: list[str] = field(default_factory=list)


def _normalize_occupation(text: str | None) -> str | None:
    if not text:
        return None
    cleaned = re.sub(r"[^\w\s]", "", text.lower()).strip()
    mapping = {
        "kisan": "farmer",
        "farmer": "farmer",
        "farming": "farmer",
        "agriculture": "farmer",
        "vendor": "street_vendor",
        "street vendor": "street_vendor",
        "hawker": "street_vendor",
        "thela": "street_vendor",
        "artisan": "artisan",
        "karigar": "artisan",
        "craftsman": "artisan",
        "carpenter": "artisan",
        "weaver": "artisan",
        "student": "student",
        "padhai": "student",
        "unemployed": "unemployed",
        "berojgar": "unemployed",
        "self employed": "self_employed",
        "business": "self_employed",
        "shopkeeper": "self_employed",
        "laborer": "laborer",
        "mazdoor": "laborer",
    }
    for k, v in mapping.items():
        if k in cleaned or cleaned in k:
            return v
    return cleaned


def evaluate_scheme(scheme: SchemeDefinition, profile: UserProfile) -> EligibilityResult:
    """Evaluate a user profile against a scheme using deterministic pure code."""
    crit = scheme.criteria
    disqualifications: list[str] = []
    missing: list[str] = []

    # 1. Age check
    if profile.age is not None:
        if crit.min_age is not None and profile.age < crit.min_age:
            disqualifications.append(f"Age {profile.age} is below minimum age of {crit.min_age}")
        if crit.max_age is not None and profile.age > crit.max_age:
            disqualifications.append(f"Age {profile.age} exceeds maximum age of {crit.max_age}")
    elif crit.min_age is not None or crit.max_age is not None:
        missing.append("age")

    # 2. Income check
    if profile.annual_income_inr is not None:
        if (
            crit.max_annual_income_inr is not None
            and profile.annual_income_inr > crit.max_annual_income_inr
        ):
            inc = profile.annual_income_inr
            ceil = crit.max_annual_income_inr
            disqualifications.append(f"Income of {inc:,} INR exceeds ceiling of {ceil:,} INR")
    elif crit.max_annual_income_inr is not None:
        missing.append("annual_income_inr")

    # 3. Occupation check
    norm_occ = _normalize_occupation(profile.occupation)
    allowed_occ = [o.lower() for o in crit.allowed_occupations]
    if "any" not in allowed_occ:
        if norm_occ:
            if norm_occ not in allowed_occ and not any(o in norm_occ for o in allowed_occ):
                target_str = ", ".join(crit.allowed_occupations)
                disqualifications.append(
                    f"Occupation '{profile.occupation}' does not match target ({target_str})"
                )
        else:
            missing.append("occupation")

    # 4. Gender check
    if "all" not in [g.lower() for g in crit.allowed_genders]:
        if profile.gender:
            if profile.gender.lower() not in [g.lower() for g in crit.allowed_genders]:
                disqualifications.append(f"Scheme is designated for {crit.allowed_genders}")
        else:
            missing.append("gender")

    # 5. Landowner check
    if crit.requires_landowner is True:
        if profile.is_landowner is False:
            disqualifications.append("Requires cultivable land ownership")
        elif profile.is_landowner is None:
            missing.append("is_landowner")

    if disqualifications:
        return EligibilityResult(
            scheme=scheme,
            status="disqualified",
            reasons=disqualifications,
        )

    if missing:
        return EligibilityResult(
            scheme=scheme,
            status="missing_info",
            reasons=[f"Missing info for: {', '.join(missing)}"],
            missing_fields=missing,
        )

    return EligibilityResult(
        scheme=scheme,
        status="eligible",
        reasons=["All eligibility criteria met"],
    )


class SchemeRepository:
    """Repository loading and searching curated government schemes."""

    def __init__(self, data_path: Path | None = None) -> None:
        path = data_path or Path(__file__).resolve().parent.parent / "data" / "schemes.json"
        self._schemes: list[SchemeDefinition] = []
        if path.is_file():
            raw_data = json.loads(path.read_text(encoding="utf-8"))
            for entry in raw_data:
                crit = entry.get("criteria", {})
                self._schemes.append(
                    SchemeDefinition(
                        id=str(entry["id"]),
                        name=str(entry["name"]),
                        category=str(entry.get("category", "general")),
                        beneficiary_desc=str(entry.get("beneficiary_desc", "")),
                        benefits_summary=str(entry.get("benefits_summary", "")),
                        official_portal_url=str(entry.get("official_portal_url", "")),
                        last_verified_date=str(entry.get("last_verified_date", "")),
                        criteria=SchemeCriteria(
                            min_age=crit.get("min_age"),
                            max_age=crit.get("max_age"),
                            max_annual_income_inr=crit.get("max_annual_income_inr"),
                            allowed_occupations=crit.get("allowed_occupations", ["any"]),
                            allowed_genders=crit.get("allowed_genders", ["all"]),
                            allowed_states=crit.get("allowed_states", ["all"]),
                            requires_landowner=crit.get("requires_landowner"),
                        ),
                    )
                )

    @property
    def all_schemes(self) -> list[SchemeDefinition]:
        return list(self._schemes)

    def find_by_name_or_id(self, query: str) -> SchemeDefinition | None:
        clean = query.strip().lower()
        for s in self._schemes:
            if s.id.lower() == clean or s.name.lower() == clean:
                return s
        for s in self._schemes:
            if clean in s.id.lower() or clean in s.name.lower():
                return s
        names = [s.name for s in self._schemes]
        matches = difflib.get_close_matches(query, names, n=1, cutoff=0.6)
        if matches:
            for s in self._schemes:
                if s.name == matches[0]:
                    return s
        return None


def format_find_spoken(
    eligible: list[EligibilityResult],
    *,
    next_question: str | None = None,
) -> str:
    """Format matching schemes into a natural voice summary strictly under 300 characters."""
    if next_question:
        return next_question[:300]

    if not eligible:
        spoken = f"I could not find matching schemes for the provided profile. {DISCLAIMER_TEXT}"
        return spoken[:300]

    names = [e.scheme.name for e in eligible[:2]]
    joined = " and ".join(names)
    spoken = f"You may qualify for {joined}. {DISCLAIMER_TEXT}"
    if len(spoken) > 300:
        spoken = spoken[:297] + "..."
    return spoken


def format_explain_spoken(scheme: SchemeDefinition) -> str:
    """Format single scheme explanation under 300 characters with source link."""
    domain = scheme.official_portal_url.replace("https://", "").replace("http://", "").rstrip("/")
    spoken = f"{scheme.name}: {scheme.benefits_summary} Apply at {domain}. {DISCLAIMER_TEXT}"
    if len(spoken) > 300:
        spoken = spoken[:297] + "..."
    return spoken


def format_check_spoken(res: EligibilityResult) -> str:
    """Format eligibility verification under 300 characters with statutory guidance."""
    if res.status == "eligible":
        spoken = (
            f"You appear eligible for {res.scheme.name} based on provided details. "
            f"{DISCLAIMER_TEXT}"
        )
    elif res.status == "disqualified":
        reason_str = res.reasons[0] if res.reasons else "criteria not satisfied"
        spoken = (
            f"You do not meet the criteria for {res.scheme.name}: {reason_str}. {DISCLAIMER_TEXT}"
        )
    else:
        field_name = res.missing_fields[0] if res.missing_fields else "required information"
        spoken = (
            f"To determine eligibility for {res.scheme.name}, please provide your {field_name}. "
            f"{DISCLAIMER_TEXT}"
        )

    if len(spoken) > 300:
        spoken = spoken[:297] + "..."
    return spoken
