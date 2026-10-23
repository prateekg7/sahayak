"""Shared LLM port, fake fixtures, router, and budget management."""

from __future__ import annotations

from sahayak.shared.llm.budget import DailyBudgetManager
from sahayak.shared.llm.circuit_breaker import CircuitBreaker, CircuitState
from sahayak.shared.llm.fake import FakeLLMClient
from sahayak.shared.llm.gemini import GeminiClient
from sahayak.shared.llm.groq import GroqClient
from sahayak.shared.llm.ports import (
    BudgetExceededError,
    CircuitBreakerOpenError,
    InvalidLLMResponseError,
    LLMClient,
    LLMError,
    LLMResponse,
    LLMTimeoutError,
    ProviderUnavailableError,
    TokenUsage,
)
from sahayak.shared.llm.router import LLMRouter

__all__ = [
    "BudgetExceededError",
    "CircuitBreaker",
    "CircuitBreakerOpenError",
    "CircuitState",
    "DailyBudgetManager",
    "FakeLLMClient",
    "GeminiClient",
    "GroqClient",
    "InvalidLLMResponseError",
    "LLMClient",
    "LLMError",
    "LLMResponse",
    "LLMRouter",
    "LLMTimeoutError",
    "ProviderUnavailableError",
    "TokenUsage",
]
