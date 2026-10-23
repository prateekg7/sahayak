"""Unit tests for topic brief domain, service, and MCP tool (T3.14)."""

from __future__ import annotations

from typing import Any

import fakeredis.aioredis
import pytest

from sahayak.core.auth.principal import Principal, set_current_principal
from sahayak.core.cache import Cache
from sahayak.core.errors import NotFoundError
from sahayak.modules.academics.service.brief import TopicBriefService
from sahayak.modules.academics.tools.brief import set_brief_service, topic_brief
from sahayak.shared.content.wikipedia import GroundingResult, WikipediaClient
from sahayak.shared.llm.fake import FakeLLMClient


class MockWikipediaClient(WikipediaClient):
    """Fake WikipediaClient returning deterministic grounding."""

    def __init__(self, groundings: dict[str, GroundingResult] | None = None) -> None:
        super().__init__()
        self._groundings = groundings or {}
        self.call_count = 0

    async def get_grounding(
        self,
        topic: str,
        *,
        language: str = "en",
        max_chars: int = 2000,
        timeout: float = 5.0,
    ) -> GroundingResult | None:
        self.call_count += 1
        return self._groundings.get(topic.lower())


@pytest.fixture
def sample_grounding() -> GroundingResult:
    extract_text = (
        "Photosynthesis is a biological process used by plants and other organisms to "
        "convert light energy into chemical energy that can later be released to fuel "
        "the organism's activities. This chemical energy is stored in carbohydrate molecules."
    )
    return GroundingResult(
        title="Photosynthesis",
        raw_extract=extract_text,
        sanitized_text=extract_text,
        wrapped_prompt_text="<grounded_source_data>Photosynthesis...</grounded_source_data>",
        url="https://en.wikipedia.org/wiki/Photosynthesis",
    )


@pytest.mark.asyncio
async def test_topic_brief_with_llm_summarization(sample_grounding: GroundingResult) -> None:
    """TopicBriefService summarizes grounding text using LLMClient when available."""
    wiki = MockWikipediaClient({"photosynthesis": sample_grounding})
    fake_llm = FakeLLMClient(
        canned_json={
            "brief": (
                "Photosynthesis is the biological process where plants convert sunlight "
                "into chemical energy. It produces oxygen and glucose."
            )
        }
    )

    service = TopicBriefService(wikipedia=wiki, llm_client=fake_llm)
    spoken, data, next_actions = await service.get_topic_brief("Photosynthesis", length="short")

    assert "Photosynthesis is the biological process" in spoken
    assert len(spoken) <= 300
    assert data.topic == "photosynthesis"
    assert data.display_name == "Photosynthesis"
    assert len(data.sources) == 1
    assert data.sources[0].title == "Photosynthesis"
    assert data.sources[0].url == "https://en.wikipedia.org/wiki/Photosynthesis"
    assert any("quiz me on Photosynthesis" in action for action in next_actions)


@pytest.mark.asyncio
async def test_topic_brief_fallback_to_extract_when_llm_fails(
    sample_grounding: GroundingResult,
) -> None:
    """When LLM generation fails, service falls back to sanitized Wikipedia extract."""
    wiki = MockWikipediaClient({"photosynthesis": sample_grounding})

    class FailingLLMClient(FakeLLMClient):
        async def generate_structured(self, **kwargs: Any) -> Any:
            raise RuntimeError("LLM rate limit or connection failure")

    service = TopicBriefService(wikipedia=wiki, llm_client=FailingLLMClient())
    spoken, data, next_actions = await service.get_topic_brief("Photosynthesis", length="short")

    assert "Photosynthesis is a biological process" in spoken
    assert len(spoken) <= 300
    assert data.brief.endswith(".")
    assert len(data.sources) == 1


@pytest.mark.asyncio
async def test_topic_brief_short_and_medium_lengths(sample_grounding: GroundingResult) -> None:
    """Short and medium briefs respect their distinct character bounds."""
    wiki = MockWikipediaClient({"photosynthesis": sample_grounding})
    service = TopicBriefService(wikipedia=wiki, llm_client=None)

    spoken_short, data_short, _ = await service.get_topic_brief("Photosynthesis", length="short")
    spoken_med, data_med, _ = await service.get_topic_brief("Photosynthesis", length="medium")

    assert len(data_short.brief) <= 240
    assert len(data_med.brief) <= 450
    assert len(spoken_short) <= 295
    assert len(spoken_med) <= 295
    assert len(data_med.brief) >= len(data_short.brief)


@pytest.mark.asyncio
async def test_topic_brief_not_found_raises_error() -> None:
    """Non-existent topic raises NotFoundError with voice-friendly message."""
    wiki = MockWikipediaClient({})
    service = TopicBriefService(wikipedia=wiki)

    with pytest.raises(NotFoundError) as exc_info:
        await service.get_topic_brief("Unicorn Gravitation 99")

    assert "I couldn't find a topic brief" in exc_info.value.spoken
    assert exc_info.value.code == "not_found"


@pytest.mark.asyncio
async def test_topic_brief_caching_avoids_repeated_fetches(
    sample_grounding: GroundingResult,
) -> None:
    """Second call for same topic and length serves from cache without wiki re-fetch."""
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    cache = Cache(redis)
    wiki = MockWikipediaClient({"photosynthesis": sample_grounding})
    service = TopicBriefService(wikipedia=wiki, cache=cache)

    # First call: hits wiki
    await service.get_topic_brief("Photosynthesis", length="short")
    assert wiki.call_count == 1

    # Second call: served from cache
    await service.get_topic_brief("Photosynthesis", length="short")
    assert wiki.call_count == 1


@pytest.mark.asyncio
async def test_topic_brief_tool_execution_and_anonymous_allowed(
    sample_grounding: GroundingResult,
) -> None:
    """MCP tool allows anonymous users and returns standard envelope."""
    wiki = MockWikipediaClient({"photosynthesis": sample_grounding})
    service = TopicBriefService(wikipedia=wiki)
    set_brief_service(service)

    try:
        # 1. Anonymous user succeeds
        set_current_principal(Principal(user_id=None, anonymous=True))
        envelope = await topic_brief(topic="Photosynthesis", length="short")
        assert envelope.get("ok") is True
        assert "Photosynthesis" in envelope.get("spoken_summary", "")
        data = envelope.get("data", {})
        assert data.get("topic") == "photosynthesis"
        assert len(data.get("sources", [])) == 1

        # 2. Invalid length returns invalid_input
        bad_envelope = await topic_brief(topic="Photosynthesis", length="ultra_long")
        assert bad_envelope.get("ok") is False
        assert bad_envelope.get("error_code") == "invalid_input"
    finally:
        set_brief_service(None)
