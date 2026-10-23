"""Unit and mocked tests for Groq adapter and router fallback integration (T2.3)."""

from __future__ import annotations

import httpx
import pytest
import respx
from pydantic import BaseModel, Field

from sahayak.shared.llm.gemini import GEMINI_BASE_URL, GeminiClient
from sahayak.shared.llm.groq import DEFAULT_GROQ_MODEL, GROQ_ENDPOINT, GroqClient
from sahayak.shared.llm.ports import (
    InvalidLLMResponseError,
    ProviderUnavailableError,
)
from sahayak.shared.llm.router import LLMRouter


class SampleFlashcard(BaseModel):
    """Schema for structured flashcard generation."""

    front: str = Field(min_length=3)
    back: str = Field(min_length=3)


@pytest.mark.asyncio
@respx.mock
async def test_groq_generate_text_success() -> None:
    """GroqClient executes chat completion and extracts usage."""
    respx.post(GROQ_ENDPOINT).mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": "Mitochondria is the powerhouse of the cell."}}
                ],
                "usage": {
                    "prompt_tokens": 12,
                    "completion_tokens": 20,
                    "total_tokens": 32,
                },
            },
            headers={"x-ratelimit-remaining-requests": "25"},
        )
    )

    client = GroqClient(api_key="test-groq-key")
    res = await client.generate_text("Define mitochondria")

    assert res.content == "Mitochondria is the powerhouse of the cell."
    assert res.provider == "groq"
    assert res.model == DEFAULT_GROQ_MODEL
    assert res.usage.total_tokens == 32


@pytest.mark.asyncio
@respx.mock
async def test_groq_generate_json_success() -> None:
    """GroqClient generates and parses JSON into the Pydantic schema."""
    respx.post(GROQ_ENDPOINT).mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"front": "What is DNA?", "back": "Deoxyribonucleic acid"}'
                        }
                    }
                ],
                "usage": {
                    "prompt_tokens": 15,
                    "completion_tokens": 15,
                    "total_tokens": 30,
                },
            },
        )
    )

    client = GroqClient(api_key="test-groq-key")
    res = await client.generate_json("Generate flashcard", schema=SampleFlashcard)

    assert isinstance(res.parsed, SampleFlashcard)
    assert res.parsed.front == "What is DNA?"
    assert res.parsed.back == "Deoxyribonucleic acid"


@pytest.mark.asyncio
async def test_groq_missing_api_key_raises_error() -> None:
    """GroqClient raises ProviderUnavailableError if API key is not configured."""
    client = GroqClient(api_key=None)
    client._api_key = None
    with pytest.raises(ProviderUnavailableError) as exc_info:
        await client.generate_text("Prompt")
    assert "Groq API key is not configured" in str(exc_info.value.detail)


@pytest.mark.asyncio
@respx.mock
async def test_groq_auth_failure() -> None:
    """GroqClient classifies 401 as ProviderUnavailableError."""
    respx.post(GROQ_ENDPOINT).mock(return_value=httpx.Response(401, text="Invalid API key"))

    client = GroqClient(api_key="invalid-key")
    with pytest.raises(ProviderUnavailableError) as exc_info:
        await client.generate_text("Prompt")
    assert "Groq authentication failed" in str(exc_info.value.detail)


@pytest.mark.asyncio
@respx.mock
async def test_groq_rate_limit_failure() -> None:
    """GroqClient classifies 429 as ProviderUnavailableError."""
    respx.post(GROQ_ENDPOINT).mock(return_value=httpx.Response(429, text="Rate limit exceeded"))

    client = GroqClient(api_key="test-key")
    with pytest.raises(ProviderUnavailableError) as exc_info:
        await client.generate_text("Prompt")
    assert "Groq rate limit exceeded" in str(exc_info.value.detail)


@pytest.mark.asyncio
@respx.mock
async def test_groq_invalid_json_format() -> None:
    """GroqClient raises InvalidLLMResponseError on unparseable JSON."""
    respx.post(GROQ_ENDPOINT).mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Not JSON at all"}}]},
        )
    )

    client = GroqClient(api_key="test-key")
    with pytest.raises(InvalidLLMResponseError) as exc_info:
        await client.generate_json("Prompt", schema=SampleFlashcard)
    assert "not valid JSON" in str(exc_info.value.detail)


@pytest.mark.asyncio
@respx.mock
async def test_router_integration_gemini_failure_to_groq_success() -> None:
    """End-to-end router test: Gemini 500 fails and falls back to Groq successfully."""
    gemini_url = f"{GEMINI_BASE_URL}/gemini-2.5-flash:generateContent"
    respx.post(gemini_url).mock(return_value=httpx.Response(500, text="Internal Google Error"))

    respx.post(GROQ_ENDPOINT).mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"front": "What is RNA?", "back": "Ribonucleic acid"}'
                        }
                    }
                ],
                "usage": {"total_tokens": 20},
            },
        )
    )

    gemini = GeminiClient(api_key="gemini-key", default_model="gemini-2.5-flash")
    groq = GroqClient(api_key="groq-key")
    router = LLMRouter(primary=gemini, fallback=groq, max_retries=0)

    res = await router.generate_json("Generate RNA card", schema=SampleFlashcard)
    assert res.provider == "groq"
    assert isinstance(res.parsed, SampleFlashcard)
    assert res.parsed.front == "What is RNA?"
