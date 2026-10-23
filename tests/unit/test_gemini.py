"""Unit and mocked contract tests for Google Gemini adapter (T2.2)."""

from __future__ import annotations

import os

import httpx
import pytest
import respx
from pydantic import BaseModel, Field

from sahayak.shared.llm.gemini import (
    DEFAULT_GEMINI_MODEL,
    GEMINI_BASE_URL,
    GeminiClient,
)
from sahayak.shared.llm.ports import (
    InvalidLLMResponseError,
    ProviderUnavailableError,
)


class SampleStudyPlan(BaseModel):
    """Schema for structured plan generation."""

    topic: str
    steps: list[str] = Field(min_length=1)
    estimated_minutes: int


@pytest.mark.asyncio
@respx.mock
async def test_gemini_generate_text_success() -> None:
    """GeminiClient parses text output and tracks token counts."""
    target_url = f"{GEMINI_BASE_URL}/{DEFAULT_GEMINI_MODEL}:generateContent"
    respx.post(target_url).mock(
        return_value=httpx.Response(
            200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": "Photosynthesis is the process..."}]}}
                ],
                "usageMetadata": {
                    "promptTokenCount": 15,
                    "candidatesTokenCount": 35,
                    "totalTokenCount": 50,
                },
            },
        )
    )

    client = GeminiClient(api_key="test-api-key")
    res = await client.generate_text("Explain photosynthesis")

    assert res.content == "Photosynthesis is the process..."
    assert res.provider == "gemini"
    assert res.usage.prompt_tokens == 15
    assert res.usage.completion_tokens == 35
    assert res.usage.total_tokens == 50


@pytest.mark.asyncio
@respx.mock
async def test_gemini_generate_json_success() -> None:
    """GeminiClient parses and validates structured JSON into Pydantic model."""
    target_url = f"{GEMINI_BASE_URL}/{DEFAULT_GEMINI_MODEL}:generateContent"
    respx.post(target_url).mock(
        return_value=httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": (
                                        '{"topic": "Calculus", "steps": ["Limits", "Derivatives"], '
                                        '"estimated_minutes": 60}'
                                    )
                                }
                            ]
                        }
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 20,
                    "candidatesTokenCount": 25,
                    "totalTokenCount": 45,
                },
            },
        )
    )

    client = GeminiClient(api_key="test-api-key")
    res = await client.generate_json("Create a study plan", schema=SampleStudyPlan)

    assert isinstance(res.parsed, SampleStudyPlan)
    assert res.parsed.topic == "Calculus"
    assert res.parsed.steps == ["Limits", "Derivatives"]
    assert res.parsed.estimated_minutes == 60


@pytest.mark.asyncio
async def test_gemini_missing_api_key_raises_error() -> None:
    """GeminiClient raises ProviderUnavailableError if API key is not configured."""
    client = GeminiClient(api_key=None)
    client._api_key = None
    with pytest.raises(ProviderUnavailableError) as exc_info:
        await client.generate_text("Prompt")
    assert "API key is not configured" in str(exc_info.value.detail)


@pytest.mark.asyncio
@respx.mock
async def test_gemini_auth_error_classification() -> None:
    """GeminiClient classifies 401 and 403 as ProviderUnavailableError."""
    target_url = f"{GEMINI_BASE_URL}/{DEFAULT_GEMINI_MODEL}:generateContent"
    respx.post(target_url).mock(return_value=httpx.Response(403, text="Forbidden key"))

    client = GeminiClient(api_key="bad-key")
    with pytest.raises(ProviderUnavailableError) as exc_info:
        await client.generate_text("Prompt")
    assert "authentication failed" in str(exc_info.value.detail)


@pytest.mark.asyncio
@respx.mock
async def test_gemini_rate_limit_classification() -> None:
    """GeminiClient classifies 429 as ProviderUnavailableError."""
    target_url = f"{GEMINI_BASE_URL}/{DEFAULT_GEMINI_MODEL}:generateContent"
    respx.post(target_url).mock(return_value=httpx.Response(429, text="Rate limit exceeded"))

    client = GeminiClient(api_key="test-key")
    with pytest.raises(ProviderUnavailableError) as exc_info:
        await client.generate_text("Prompt")
    assert "rate limit exceeded" in str(exc_info.value.detail)


@pytest.mark.asyncio
@respx.mock
async def test_gemini_invalid_json_output() -> None:
    """GeminiClient raises InvalidLLMResponseError when output is malformed JSON."""
    target_url = f"{GEMINI_BASE_URL}/{DEFAULT_GEMINI_MODEL}:generateContent"
    respx.post(target_url).mock(
        return_value=httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": "Not valid JSON at all"}]}}]},
        )
    )

    client = GeminiClient(api_key="test-key")
    with pytest.raises(InvalidLLMResponseError) as exc_info:
        await client.generate_json("Prompt", schema=SampleStudyPlan)
    assert "not valid JSON" in str(exc_info.value.detail)


@pytest.mark.asyncio
@respx.mock
async def test_gemini_schema_validation_failure() -> None:
    """GeminiClient raises InvalidLLMResponseError when JSON fails schema constraints."""
    target_url = f"{GEMINI_BASE_URL}/{DEFAULT_GEMINI_MODEL}:generateContent"
    respx.post(target_url).mock(
        return_value=httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": (
                                        '{"topic": "Calculus", "steps": [], '
                                        '"estimated_minutes": 60}'
                                    )
                                }
                            ]
                        }
                    }
                ]
            },
        )
    )

    client = GeminiClient(api_key="test-key")
    with pytest.raises(InvalidLLMResponseError) as exc_info:
        await client.generate_json("Prompt", schema=SampleStudyPlan)
    assert "failed validation" in str(exc_info.value.detail)


@pytest.mark.live
@pytest.mark.asyncio
async def test_gemini_live_opt_in() -> None:
    """Live opt-in call to Google Gemini endpoint when GEMINI_API_KEY is present."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        pytest.skip("GEMINI_API_KEY not provided for live test")

    client = GeminiClient(api_key=api_key)
    res = await client.generate_json(
        "Generate a study plan for high school trigonometry with 2 steps",
        schema=SampleStudyPlan,
    )
    assert isinstance(res.parsed, SampleStudyPlan)
    assert len(res.parsed.steps) >= 1
