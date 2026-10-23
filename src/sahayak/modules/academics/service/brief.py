"""Service orchestrating grounded topic briefs with Wikipedia and LLM (T3.14)."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

from sahayak.core.errors import NotFoundError
from sahayak.modules.academics.domain.topics import normalize_topic
from sahayak.modules.academics.schemas import (
    BriefLength,
    RawTopicBriefOutput,
    TopicBriefResponseData,
    TopicBriefSource,
)
from sahayak.shared.content.wikipedia import WikipediaClient
from sahayak.shared.llm.ports import LLMClient

if TYPE_CHECKING:
    from sahayak.core.cache import Cache

logger = logging.getLogger(__name__)

PROMPT_PATH = Path("prompts/topic_brief_v1.md")
DEFAULT_CACHE_TTL_DAYS = 7

# Spoken and data length limits
MAX_SHORT_CHARS = 240
MAX_MEDIUM_CHARS = 450
MAX_SPOKEN_CHARS = 295


_FORBIDDEN_CHARS_PATTERN = re.compile(r"[*_~`#\[\](){}<>|\\]|https?://|[\U0001F600-\U0001FAFF]")


def _clean_voice_text(text: str) -> str:
    """Strip markdown, URLs, symbols, and excess whitespace."""
    cleaned = _FORBIDDEN_CHARS_PATTERN.sub("", text)
    return re.sub(r"\s+", " ", cleaned).strip()


def _truncate_to_sentence(text: str, max_len: int) -> str:
    """Truncate text to the last complete sentence within max_len."""
    if len(text) <= max_len:
        return text

    truncated = text[:max_len]
    last_punct = max(truncated.rfind(". "), truncated.rfind("! "), truncated.rfind("? "))
    if last_punct > 40:
        return truncated[: last_punct + 1]

    # Fallback to word boundary
    last_space = truncated.rfind(" ")
    if last_space > 40:
        return truncated[:last_space].rstrip(".,;") + "."

    return truncated.rstrip(".,;") + "."


class TopicBriefService:
    """Retrieves grounded Wikipedia facts and summarizes them into concise voice briefs."""

    def __init__(
        self,
        *,
        wikipedia: WikipediaClient | None = None,
        llm_client: LLMClient | None = None,
        cache: Cache | None = None,
    ) -> None:
        self._wikipedia = wikipedia or WikipediaClient(cache=cache)
        self._llm_client = llm_client
        self._cache = cache

    async def get_topic_brief(
        self,
        topic: str,
        length: BriefLength = "short",
    ) -> tuple[str, TopicBriefResponseData, list[str]]:
        """Generate a sourced, grounded brief for an academic topic.

        Args:
            topic: Raw topic string or query.
            length: Summary length variant ('short' or 'medium').

        Returns:
            Tuple of (spoken_summary, response_data, next_actions).

        Raises:
            NotFoundError: When no relevant grounding reference can be located.
        """
        topic_key, display_name = normalize_topic(topic)
        cache_key = f"topic_brief:{topic_key}:{length}"

        # 1. Check Redis cache
        if self._cache is not None:
            try:
                cached_data = await self._cache.get_json(cache_key)
                if cached_data and isinstance(cached_data, dict):
                    data = TopicBriefResponseData.model_validate(cached_data.get("data", {}))
                    spoken = str(cached_data.get("spoken_summary", data.brief))
                    next_actions = list(cached_data.get("next_actions", []))
                    return spoken, data, next_actions
            except Exception as exc:
                logger.warning("Cache read failed for %s: %s", cache_key, exc)

        # 2. Fetch grounding from Wikipedia
        grounding = await self._wikipedia.get_grounding(display_name)
        if grounding is None or not grounding.raw_extract.strip():
            # Try searching with canonical key as fallback
            grounding = await self._wikipedia.get_grounding(topic_key)

        if grounding is None or not grounding.raw_extract.strip():
            raise NotFoundError(
                spoken=(
                    f"I couldn't find a topic brief for {display_name}. Please try another topic."
                ),
                detail=f"No Wikipedia grounding found for topic '{topic}' (key='{topic_key}')",
            )

        sources = [TopicBriefSource(title=grounding.title, url=grounding.url)]
        brief_text: str | None = None

        # 3. LLM Summarization
        if self._llm_client is not None:
            try:
                prompt_text = PROMPT_PATH.read_text(encoding="utf-8")
                assembled_prompt = prompt_text.format(
                    topic=display_name,
                    length=length,
                    grounding_text=grounding.sanitized_text,
                )
                llm_response = await self._llm_client.generate_json(
                    prompt=assembled_prompt,
                    schema=RawTopicBriefOutput,
                )
                raw_output: RawTopicBriefOutput | None = None
                if isinstance(llm_response.parsed, RawTopicBriefOutput):
                    raw_output = llm_response.parsed
                elif isinstance(llm_response.parsed, dict):
                    raw_output = RawTopicBriefOutput.model_validate(llm_response.parsed)

                if raw_output and raw_output.brief:
                    candidate_brief = _clean_voice_text(raw_output.brief)
                    if candidate_brief:
                        max_chars = MAX_SHORT_CHARS if length == "short" else MAX_MEDIUM_CHARS
                        brief_text = _truncate_to_sentence(candidate_brief, max_chars)
            except Exception as exc:
                logger.warning(
                    "LLM topic brief generation failed for %s; falling back to extract: %s",
                    display_name,
                    exc,
                )

        # 4. Fallback to sanitized extract
        if not brief_text:
            cleaned_extract = _clean_voice_text(grounding.sanitized_text)
            max_chars = MAX_SHORT_CHARS if length == "short" else MAX_MEDIUM_CHARS
            brief_text = _truncate_to_sentence(cleaned_extract, max_chars)

        # 5. Determine voice-safe spoken summary
        spoken_summary = _truncate_to_sentence(brief_text, MAX_SPOKEN_CHARS)

        # 6. Assemble next actions
        next_actions = [
            f"Say 'quiz me on {display_name}' to practice.",
            f"Say 'create flashcards for {display_name}' to study.",
        ]

        data = TopicBriefResponseData(
            topic=topic_key,
            display_name=display_name,
            brief=brief_text,
            length=length,
            sources=sources,
        )

        # 7. Write to cache
        if self._cache is not None:
            try:
                payload = {
                    "spoken_summary": spoken_summary,
                    "data": data.model_dump(),
                    "next_actions": next_actions,
                }
                ttl_seconds = DEFAULT_CACHE_TTL_DAYS * 86400
                await self._cache.set_json(cache_key, payload, ttl_seconds=ttl_seconds)
            except Exception as exc:
                logger.warning("Cache write failed for %s: %s", cache_key, exc)

        return spoken_summary, data, next_actions
