"""Deterministic fake LLM client for tests and offline harnesses."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from sahayak.shared.llm.ports import (
    InvalidLLMResponseError,
    LLMClient,
    LLMResponse,
    TokenUsage,
)

if TYPE_CHECKING:
    pass


class FakeLLMClient(LLMClient):
    """Deterministic, scriptable in-memory implementation of ``LLMClient``."""

    def __init__(
        self,
        *,
        provider_name: str = "fake",
        default_model: str = "fake-model-1",
        canned_text: str | list[str] | None = None,
        canned_json: Any | list[Any] | None = None,
        scripted_errors: list[Exception] | None = None,
        latency_seconds: float = 0.0,
        usage: TokenUsage | None = None,
    ) -> None:
        self._provider_name = provider_name
        self.default_model = default_model
        if isinstance(canned_text, list):
            self.canned_text_queue: list[str] = list(canned_text)
        elif canned_text is not None:
            self.canned_text_queue = [canned_text]
        else:
            self.canned_text_queue = []
        if isinstance(canned_json, list):
            self.canned_json_queue: list[Any] = list(canned_json)
        elif canned_json is not None:
            self.canned_json_queue = [canned_json]
        else:
            self.canned_json_queue = []
        self.scripted_errors: list[Exception] = list(scripted_errors or [])
        self.latency_seconds = latency_seconds
        self.usage = usage or TokenUsage(prompt_tokens=40, completion_tokens=60, total_tokens=100)
        self.history: list[dict[str, Any]] = []

    @property
    def provider_name(self) -> str:
        return self._provider_name

    def queue_text(self, text: str) -> None:
        """Add a response string to the text queue."""
        self.canned_text_queue.append(text)

    def queue_json(self, value: Any) -> None:
        """Add a JSON object or model to the JSON queue."""
        self.canned_json_queue.append(value)

    def queue_error(self, exc: Exception) -> None:
        """Add an exception to raise on the next invocation."""
        self.scripted_errors.append(exc)

    async def generate_text(
        self,
        prompt: str,
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        timeout: float = 8.0,
    ) -> LLMResponse:
        self.history.append(
            {
                "type": "text",
                "prompt": prompt,
                "model": model or self.default_model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "timeout": timeout,
            }
        )

        if self.latency_seconds > 0:
            await asyncio.sleep(self.latency_seconds)

        if self.scripted_errors:
            raise self.scripted_errors.pop(0)

        content = (
            self.canned_text_queue.pop(0)
            if self.canned_text_queue
            else "Default synthetic text response"
        )
        return LLMResponse(
            content=content,
            parsed=None,
            usage=self.usage,
            model=model or self.default_model,
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
        self.history.append(
            {
                "type": "json",
                "prompt": prompt,
                "schema": schema,
                "model": model or self.default_model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "timeout": timeout,
            }
        )

        if self.latency_seconds > 0:
            await asyncio.sleep(self.latency_seconds)

        if self.scripted_errors:
            raise self.scripted_errors.pop(0)

        raw_item: Any = self.canned_json_queue.pop(0) if self.canned_json_queue else {}

        parsed_output: Any
        content_str: str

        if isinstance(raw_item, BaseModel):
            parsed_output = raw_item
            content_str = raw_item.model_dump_json()
        elif isinstance(schema, type) and issubclass(schema, BaseModel):
            try:
                if isinstance(raw_item, str):
                    parsed_output = schema.model_validate_json(raw_item)
                    content_str = raw_item
                elif isinstance(raw_item, dict):
                    parsed_output = schema.model_validate(raw_item)
                    content_str = json.dumps(raw_item)
                else:
                    detail = (
                        f"Cannot validate canned item {type(raw_item)} against {schema.__name__}"
                    )
                    raise InvalidLLMResponseError(detail=detail)
            except Exception as exc:
                detail = f"Failed to validate response against schema {schema.__name__}: {exc}"
                raise InvalidLLMResponseError(detail=detail) from exc
        else:
            parsed_output = raw_item
            content_str = json.dumps(raw_item) if isinstance(raw_item, dict) else str(raw_item)

        return LLMResponse(
            content=content_str,
            parsed=parsed_output,
            usage=self.usage,
            model=model or self.default_model,
            provider=self.provider_name,
        )
