"""Abstract port and value objects for language model providers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from sahayak.core.errors import UpstreamUnavailableError

if TYPE_CHECKING:
    from pydantic import BaseModel


@dataclass(frozen=True)
class TokenUsage:
    """Token consumption for an LLM request."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class LLMResponse:
    """Standardized response from an LLM provider."""

    content: str
    parsed: Any = None
    usage: TokenUsage = field(default_factory=TokenUsage)
    model: str = ""
    provider: str = ""


class LLMError(UpstreamUnavailableError):
    """Base exception for all language model invocation errors."""

    def __init__(
        self,
        spoken: str = "I'm having trouble thinking through that right now. Please try again soon.",
        *,
        detail: str | None = None,
    ) -> None:
        super().__init__(spoken=spoken, detail=detail)


class ProviderUnavailableError(LLMError):
    """Raised when an LLM provider fails after retries or is unreachable."""


class CircuitBreakerOpenError(LLMError):
    """Raised when an LLM provider circuit is open due to repeated failures."""

    def __init__(self, provider: str, *, detail: str | None = None) -> None:
        msg = f"LLM provider circuit open for '{provider}'"
        super().__init__(
            spoken=(
                "The language service is currently experiencing high load. "
                "Please try again in a moment."
            ),
            detail=detail or msg,
        )


class BudgetExceededError(LLMError):
    """Raised when the daily request or token budget for LLM calls is exhausted."""

    def __init__(self, *, detail: str | None = None) -> None:
        super().__init__(
            spoken=(
                "I've reached my daily limit for generating new content. Please try again tomorrow."
            ),
            detail=detail or "Daily LLM request budget exhausted",
        )


class LLMTimeoutError(LLMError):
    """Raised when an LLM call exceeds its execution timeout."""


class InvalidLLMResponseError(LLMError):
    """Raised when provider output cannot be parsed into the expected schema."""


@runtime_checkable
class LLMClient(Protocol):
    """Contract that every language model adapter and router must satisfy."""

    @property
    def provider_name(self) -> str:
        """Identifier of this provider (e.g., 'gemini', 'groq', 'fake', 'router')."""
        ...

    async def generate_text(
        self,
        prompt: str,
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        timeout: float = 8.0,
    ) -> LLMResponse:
        """Generate unstructured text from a prompt.

        Args:
            prompt: Instructions and context for the model.
            model: Provider-specific model override (reads default from config).
            temperature: Sampling temperature between 0.0 and 1.0.
            max_tokens: Maximum tokens to generate in response.
            timeout: Call timeout in seconds.

        Returns:
            An LLMResponse containing the generated text and token metrics.
        """
        ...

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
        """Generate structured JSON adhering strictly to the provided schema.

        Args:
            prompt: Instructions and context for the model.
            schema: Pydantic model class or JSON Schema dictionary.
            model: Provider-specific model override.
            temperature: Sampling temperature (typically lower for structured tasks).
            max_tokens: Maximum tokens to generate.
            timeout: Call timeout in seconds.

        Returns:
            An LLMResponse where ``parsed`` contains the validated Pydantic model
            or dictionary.
        """
        ...
