"""MCP tool for government welfare scheme discovery and eligibility advice (T12.4)."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from sahayak.core.auth.principal import allow_anonymous
from sahayak.core.envelope import fail, ok
from sahayak.core.errors import InvalidInputError, SahayakError
from sahayak.core.observability.instrumentation import instrument_tool
from sahayak.modules.local_info.domain.schemes import UserProfile
from sahayak.modules.local_info.schemas import SchemeFinderRequest
from sahayak.modules.local_info.service.schemes import SchemeService

SCHEME_FINDER_DESCRIPTION = (
    "Discover government welfare schemes, check eligibility, and find portals. "
    "Use when the user asks 'Which government schemes do I qualify for?', "
    "'Tell me about PM-Kisan', or 'Am I eligible for Ayushman Bharat?'. "
    "Do not use for checking agricultural mandi prices or transit departures; "
    "use 'commodity_prices' or 'transit_status' instead."
)

_scheme_service: SchemeService | None = None


def set_scheme_service(service: SchemeService | None) -> None:
    """Configure module-level scheme service instance."""
    global _scheme_service
    _scheme_service = service


def get_scheme_service() -> SchemeService:
    """Retrieve the configured scheme service instance."""
    global _scheme_service
    if _scheme_service is None:
        _scheme_service = SchemeService()
    return _scheme_service


@allow_anonymous
async def scheme_finder(
    action: str = "find",
    scheme: str | None = None,
    age: int | None = None,
    annual_income_inr: int | None = None,
    occupation: str | None = None,
    state: str | None = None,
    gender: str | None = None,
    is_landowner: bool | None = None,
) -> dict[str, Any]:
    """Discover government welfare schemes, explain benefits, and verify qualification rules."""
    async with instrument_tool("scheme_finder", "local_info"):
        try:
            req = SchemeFinderRequest(
                action=action,  # type: ignore[arg-type]
                scheme=scheme,
                age=age,
                annual_income_inr=annual_income_inr,
                occupation=occupation,
                state=state,
                gender=gender,
                is_landowner=is_landowner,
            )
        except (ValidationError, ValueError) as err:
            return fail(
                InvalidInputError(
                    spoken=(
                        "Please specify an action of find, explain, or check_eligibility, "
                        "and provide any known profile details."
                    ),
                    detail=str(err),
                ),
                module="local_info",
                version="0.1.0",
            )

        service = get_scheme_service()
        profile = UserProfile(
            age=req.age,
            annual_income_inr=req.annual_income_inr,
            occupation=req.occupation,
            state=req.state,
            gender=req.gender,
            is_landowner=req.is_landowner,
        )

        try:
            if req.action == "find":
                spoken, data = await service.find_schemes(profile)
                next_actions = ["explain scheme", "check specific scheme eligibility"]
            elif req.action == "explain":
                if not req.scheme:
                    return fail(
                        InvalidInputError(
                            spoken="Please specify which scheme you would like explained.",
                            detail="Scheme name or slug is required for explain action.",
                        ),
                        module="local_info",
                        version="0.1.0",
                    )
                spoken, data = await service.explain_scheme(req.scheme)
                next_actions = ["check eligibility", "find other schemes"]
            elif req.action == "check_eligibility":
                if not req.scheme:
                    return fail(
                        InvalidInputError(
                            spoken="Please specify which scheme to verify eligibility for.",
                            detail="Scheme name or slug is required for check_eligibility action.",
                        ),
                        module="local_info",
                        version="0.1.0",
                    )
                spoken, data = await service.check_eligibility(req.scheme, profile)
                next_actions = ["find other schemes", "explain scheme benefits"]
            else:
                return fail(
                    InvalidInputError(
                        spoken="Action must be find, explain, or check_eligibility.",
                        detail=f"Unknown action {req.action}",
                    ),
                    module="local_info",
                    version="0.1.0",
                )

            return ok(
                spoken_summary=spoken,
                data=data,
                next_actions=next_actions,
                module="local_info",
                version="0.1.0",
            )
        except SahayakError as err:
            return fail(err, module="local_info", version="0.1.0")
