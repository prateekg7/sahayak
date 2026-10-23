"""MCP tool exposing grounded, sourced topic summaries for academic subjects (T3.14)."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from sahayak.core.auth.principal import allow_anonymous
from sahayak.core.envelope import fail, ok
from sahayak.core.errors import InvalidInputError, SahayakError
from sahayak.core.observability.instrumentation import instrument_tool
from sahayak.modules.academics.schemas import TopicBriefRequest
from sahayak.modules.academics.service.brief import TopicBriefService

TOPIC_BRIEF_DESCRIPTION = (
    "Provides a concise, sourced spoken summary of an academic topic "
    "grounded in verified references. "
    "Use when the user asks 'Give me a brief on photosynthesis', "
    "'Tell me about the French Revolution', or 'What is plate tectonics?'. "
    "Do not use for testing knowledge or scheduling study; "
    "use 'quiz_start' or 'study_plan' instead."
)

_brief_service: TopicBriefService | None = None


def set_brief_service(service: TopicBriefService | None) -> None:
    """Configure module-level brief service instance."""
    global _brief_service
    _brief_service = service


def get_brief_service() -> TopicBriefService:
    """Retrieve the configured brief service instance."""
    global _brief_service
    if _brief_service is None:
        _brief_service = TopicBriefService()
    return _brief_service


@allow_anonymous
async def topic_brief(
    topic: str,
    length: str = "short",
) -> dict[str, Any]:
    """Provide a verified, sourced spoken overview of an academic topic."""
    async with instrument_tool("topic_brief", "academics"):
        try:
            req = TopicBriefRequest(
                topic=topic,
                length=length,  # type: ignore[arg-type]
            )
        except (ValidationError, ValueError) as val_err:
            return fail(
                InvalidInputError(
                    spoken=(
                        "Please provide a valid topic name and choose a length of short or medium."
                    ),
                    detail=str(val_err),
                ),
                module="academics",
                version="0.1.0",
            )

        service = get_brief_service()

        try:
            spoken, data, next_actions = await service.get_topic_brief(
                topic=req.topic,
                length=req.length,
            )

            return ok(
                spoken_summary=spoken,
                data=data.model_dump(),
                next_actions=next_actions,
                module="academics",
                version="0.1.0",
            )
        except SahayakError as err:
            return fail(err, module="academics", version="0.1.0")
