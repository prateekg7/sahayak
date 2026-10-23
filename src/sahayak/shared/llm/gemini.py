"""Google Gemini adapter supporting text and structured JSON generation."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

import httpx
from pydantic import BaseModel

from sahayak.core.config import get_settings
from sahayak.core.security import create_safe_http_client
from sahayak.shared.llm.ports import (
    InvalidLLMResponseError,
    LLMClient,
    LLMResponse,
    ProviderUnavailableError,
    TokenUsage,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
GEMINI_ALLOWED_HOST = "generativelanguage.googleapis.com"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"


class GeminiClient(LLMClient):
    """Adapter for Google Gemini Flash generation with structured output support."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        default_model: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        settings = get_settings()
        configured_key = api_key or (
            settings.gemini_api_key.get_secret_value() if settings.gemini_api_key else None
        )
        self._api_key = configured_key
        self.default_model = default_model or settings.llm_primary_model or DEFAULT_GEMINI_MODEL
        self._http_client = http_client

    @property
    def provider_name(self) -> str:
        return "gemini"

    async def _send_request(
        self,
        payload: dict[str, Any],
        model: str,
        timeout: float,
    ) -> tuple[dict[str, Any], TokenUsage]:
        """Transmit request to Google Gemini REST endpoint and extract output."""
        if not self._api_key:
            raise ProviderUnavailableError(detail="Gemini API key is not configured")

        url = f"{GEMINI_BASE_URL}/{model}:generateContent"
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self._api_key,
        }

        async def _do_post(client: httpx.AsyncClient) -> httpx.Response:
            return await client.post(url, json=payload, headers=headers, timeout=timeout)

        try:
            if self._http_client is not None:
                response = await _do_post(self._http_client)
            else:
                async with create_safe_http_client(
                    allowed_hosts=[GEMINI_ALLOWED_HOST], timeout=timeout
                ) as client:
                    response = await _do_post(client)
        except httpx.TimeoutException as exc:
            raise ProviderUnavailableError(
                detail=f"Gemini API request timed out after {timeout}s"
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderUnavailableError(detail=f"Gemini network error: {exc}") from exc

        if response.status_code in {401, 403}:
            raise ProviderUnavailableError(
                detail=f"Gemini authentication failed (status {response.status_code})"
            )
        if response.status_code == 429:
            raise ProviderUnavailableError(detail="Gemini rate limit exceeded (status 429)")
        if response.is_client_error:
            raise InvalidLLMResponseError(
                detail=f"Gemini client error (status {response.status_code}): {response.text}"
            )
        if response.is_server_error:
            raise ProviderUnavailableError(
                detail=f"Gemini server error (status {response.status_code}): {response.text}"
            )

        data = response.json()
        candidates = data.get("candidates", [])
        if not candidates:
            raise InvalidLLMResponseError(detail="Gemini returned no candidates in response")

        usage_raw = data.get("usageMetadata", {})
        usage = TokenUsage(
            prompt_tokens=usage_raw.get("promptTokenCount", 0),
            completion_tokens=usage_raw.get("candidatesTokenCount", 0),
            total_tokens=usage_raw.get("totalTokenCount", 0),
        )

        return data, usage

    async def generate_text(
        self,
        prompt: str,
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        timeout: float = 8.0,
    ) -> LLMResponse:
        target_model = model or self.default_model
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }

        data, usage = await self._send_request(payload, model=target_model, timeout=timeout)
        content = data["candidates"][0]["content"]["parts"][0]["text"]
        return LLMResponse(
            content=content,
            parsed=None,
            usage=usage,
            model=target_model,
            provider=self.provider_name,
        )

    async def generate_json(
        self,
        prompt: str,
        schema: type[BaseModel] | dict[str, Any],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2000,
        timeout: float = 8.0,
    ) -> LLMResponse:
        target_model = model or self.default_model
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
                "responseMimeType": "application/json",
            },
        }

        data, usage = await self._send_request(payload, model=target_model, timeout=timeout)
        content = data["candidates"][0]["content"]["parts"][0]["text"]

        try:
            parsed_raw = json.loads(content)
        except json.JSONDecodeError as exc:
            raise InvalidLLMResponseError(detail=f"Gemini output is not valid JSON: {exc}") from exc

        parsed_output: Any = parsed_raw
        if isinstance(schema, type) and issubclass(schema, BaseModel):
            try:
                parsed_output = schema.model_validate(parsed_raw)
            except Exception as exc:
                raise InvalidLLMResponseError(
                    detail=f"Gemini JSON output failed validation for {schema.__name__}: {exc}"
                ) from exc

        return LLMResponse(
            content=content,
            parsed=parsed_output,
            usage=usage,
            model=target_model,
            provider=self.provider_name,
        )
