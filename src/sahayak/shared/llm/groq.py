"""Groq adapter supporting fast fallback text and structured JSON generation."""

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

GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
GROQ_ALLOWED_HOST = "api.groq.com"
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"


class GroqClient(LLMClient):
    """Adapter for Groq LPU inference as a fast secondary provider."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        default_model: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        settings = get_settings()
        configured_key = api_key or (
            settings.groq_api_key.get_secret_value() if settings.groq_api_key else None
        )
        self._api_key = configured_key
        self.default_model = default_model or settings.llm_fallback_model or DEFAULT_GROQ_MODEL
        self._http_client = http_client

    @property
    def provider_name(self) -> str:
        return "groq"

    async def _send_request(
        self,
        payload: dict[str, Any],
        timeout: float,
    ) -> tuple[dict[str, Any], TokenUsage]:
        """Transmit request to Groq OpenAI-compatible chat completions endpoint."""
        if not self._api_key:
            raise ProviderUnavailableError(detail="Groq API key is not configured")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }

        async def _do_post(client: httpx.AsyncClient) -> httpx.Response:
            return await client.post(GROQ_ENDPOINT, json=payload, headers=headers, timeout=timeout)

        try:
            if self._http_client is not None:
                response = await _do_post(self._http_client)
            else:
                async with create_safe_http_client(
                    allowed_hosts=[GROQ_ALLOWED_HOST], timeout=timeout
                ) as client:
                    response = await _do_post(client)
        except httpx.TimeoutException as exc:
            raise ProviderUnavailableError(
                detail=f"Groq API request timed out after {timeout}s"
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderUnavailableError(detail=f"Groq network error: {exc}") from exc

        # Parse rate limit telemetry from headers
        rem_req = response.headers.get("x-ratelimit-remaining-requests")
        if rem_req and rem_req.isdigit() and int(rem_req) < 5:
            logger.warning("Groq remaining requests low: %s", rem_req)

        if response.status_code in {401, 403}:
            raise ProviderUnavailableError(
                detail=f"Groq authentication failed (status {response.status_code})"
            )
        if response.status_code == 429:
            raise ProviderUnavailableError(detail="Groq rate limit exceeded (status 429)")
        if response.is_client_error:
            raise InvalidLLMResponseError(
                detail=f"Groq client error (status {response.status_code}): {response.text}"
            )
        if response.is_server_error:
            raise ProviderUnavailableError(
                detail=f"Groq server error (status {response.status_code}): {response.text}"
            )

        data = response.json()
        choices = data.get("choices", [])
        if not choices:
            raise InvalidLLMResponseError(detail="Groq returned no choices in response")

        usage_raw = data.get("usage", {})
        usage = TokenUsage(
            prompt_tokens=usage_raw.get("prompt_tokens", 0),
            completion_tokens=usage_raw.get("completion_tokens", 0),
            total_tokens=usage_raw.get("total_tokens", 0),
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
            "model": target_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        data, usage = await self._send_request(payload, timeout=timeout)
        content = data["choices"][0]["message"]["content"]
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
        system_instruction = (
            "You are an expert system. Respond strictly with a JSON object. "
            "Do not include any preamble, formatting backticks, or explanation."
        )
        payload = {
            "model": target_model,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        data, usage = await self._send_request(payload, timeout=timeout)
        content = data["choices"][0]["message"]["content"]

        try:
            parsed_raw = json.loads(content)
        except json.JSONDecodeError as exc:
            raise InvalidLLMResponseError(detail=f"Groq output is not valid JSON: {exc}") from exc

        parsed_output: Any = parsed_raw
        if isinstance(schema, type) and issubclass(schema, BaseModel):
            try:
                parsed_output = schema.model_validate(parsed_raw)
            except Exception as exc:
                raise InvalidLLMResponseError(
                    detail=f"Groq JSON output failed validation for {schema.__name__}: {exc}"
                ) from exc

        return LLMResponse(
            content=content,
            parsed=parsed_output,
            usage=usage,
            model=target_model,
            provider=self.provider_name,
        )
