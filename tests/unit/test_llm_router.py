"""Unit tests for LLM port, fake client, circuit breaker, budget, and router (T2.1)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from pydantic import BaseModel, Field

from sahayak.shared.llm.budget import DailyBudgetManager
from sahayak.shared.llm.circuit_breaker import CircuitBreaker, CircuitState
from sahayak.shared.llm.fake import FakeLLMClient
from sahayak.shared.llm.ports import (
    BudgetExceededError,
    CircuitBreakerOpenError,
    InvalidLLMResponseError,
    ProviderUnavailableError,
)
from sahayak.shared.llm.router import LLMRouter


class SampleQuizQuestion(BaseModel):
    """Schema for structured quiz question generation tests."""

    question: str = Field(min_length=5)
    options: list[str] = Field(min_length=2)
    correct_option: str


@pytest.mark.asyncio
async def test_fake_client_generate_text_and_json() -> None:
    """FakeLLMClient generates scripted text and validated JSON responses."""
    fake = FakeLLMClient(
        canned_text="What is the capital of France?",
        canned_json={
            "question": "What is the capital of France?",
            "options": ["Paris", "Lyon"],
            "correct_option": "Paris",
        },
    )

    # 1. Text generation
    text_res = await fake.generate_text("Generate a question")
    assert text_res.content == "What is the capital of France?"
    assert text_res.provider == "fake"
    assert text_res.usage.total_tokens > 0

    # 2. JSON generation with Pydantic validation
    json_res = await fake.generate_json("Generate question JSON", schema=SampleQuizQuestion)
    assert isinstance(json_res.parsed, SampleQuizQuestion)
    assert json_res.parsed.question == "What is the capital of France?"
    assert json_res.parsed.correct_option == "Paris"


@pytest.mark.asyncio
async def test_fake_client_invalid_schema_raises_error() -> None:
    """FakeLLMClient raises InvalidLLMResponseError when output violates Pydantic schema."""
    fake = FakeLLMClient(canned_json={"question": "No options"})
    with pytest.raises(InvalidLLMResponseError):
        await fake.generate_json("Prompt", schema=SampleQuizQuestion)


@pytest.mark.asyncio
async def test_router_primary_success() -> None:
    """LLMRouter routes through the primary provider when healthy."""
    primary = FakeLLMClient(provider_name="gemini", canned_text="Primary answer")
    fallback = FakeLLMClient(provider_name="groq", canned_text="Fallback answer")
    router = LLMRouter(primary=primary, fallback=fallback)

    res = await router.generate_text("Hello")
    assert res.content == "Primary answer"
    assert len(primary.history) == 1
    assert len(fallback.history) == 0


@pytest.mark.asyncio
async def test_router_fallback_on_primary_error() -> None:
    """LLMRouter automatically falls back to secondary provider on primary failure."""
    primary = FakeLLMClient(
        provider_name="gemini",
        scripted_errors=[RuntimeError("Gemini 503 Overloaded")],
    )
    fallback = FakeLLMClient(provider_name="groq", canned_text="Fallback response")
    router = LLMRouter(
        primary=primary,
        fallback=fallback,
        max_retries=0,  # fail immediately to fallback
    )

    res = await router.generate_text("Generate content")
    assert res.content == "Fallback response"
    assert len(primary.history) == 1
    assert len(fallback.history) == 1


@pytest.mark.asyncio
async def test_router_both_providers_fail_raises_provider_unavailable() -> None:
    """LLMRouter raises ProviderUnavailableError when all providers fail."""
    primary = FakeLLMClient(
        provider_name="gemini",
        scripted_errors=[RuntimeError("Gemini down")],
    )
    fallback = FakeLLMClient(
        provider_name="groq",
        scripted_errors=[RuntimeError("Groq down")],
    )
    router = LLMRouter(primary=primary, fallback=fallback, max_retries=0)

    with pytest.raises(ProviderUnavailableError) as exc_info:
        await router.generate_text("Generate content")
    assert "Both primary" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_circuit_breaker_transitions() -> None:
    """CircuitBreaker trips to OPEN on repeated failures and recovers via HALF_OPEN."""
    cb = CircuitBreaker("test-provider", failure_threshold=2, recovery_timeout_seconds=0.1)

    assert cb.state is CircuitState.CLOSED
    assert cb.can_execute() is True

    # 1 failure
    cb.record_failure()
    state_after_1: CircuitState = cb.state
    assert state_after_1 is CircuitState.CLOSED

    # 2nd failure -> trips OPEN
    cb.record_failure()
    state_after_2: CircuitState = cb.state
    assert state_after_2 is CircuitState.OPEN
    with pytest.raises(CircuitBreakerOpenError):
        cb.can_execute()

    # Wait for recovery timeout
    await asyncio.sleep(0.12)
    state_after_timeout: CircuitState = cb.state
    assert state_after_timeout is CircuitState.HALF_OPEN
    assert cb.can_execute() is True

    # Success resets to CLOSED
    cb.record_success()
    state_after_success: CircuitState = cb.state
    assert state_after_success is CircuitState.CLOSED
    assert cb.consecutive_failures == 0


@pytest.mark.asyncio
async def test_router_skips_primary_when_circuit_is_open() -> None:
    """LLMRouter routes immediately to fallback if primary circuit is open."""
    primary = FakeLLMClient(provider_name="gemini", canned_text="Primary")
    fallback = FakeLLMClient(provider_name="groq", canned_text="Fallback response")
    router = LLMRouter(primary=primary, fallback=fallback)

    # Force trip primary circuit breaker
    primary_cb = router.get_circuit_breaker("gemini")
    primary_cb.record_failure()
    primary_cb.record_failure()
    primary_cb.record_failure()
    assert primary_cb.state == CircuitState.OPEN

    res = await router.generate_text("Prompt")
    assert res.content == "Fallback response"
    assert len(primary.history) == 0  # Primary was not called at all
    assert len(fallback.history) == 1


@pytest.mark.asyncio
async def test_daily_budget_exhaustion() -> None:
    """DailyBudgetManager raises BudgetExceededError when request ceiling is reached."""
    budget = DailyBudgetManager(daily_request_limit=3)
    primary = FakeLLMClient(provider_name="gemini", canned_text="Answer")
    router = LLMRouter(primary=primary, budget_manager=budget)

    # 3 requests allowed
    await router.generate_text("Q1")
    await router.generate_text("Q2")
    await router.generate_text("Q3")

    # 4th request raises BudgetExceededError
    with pytest.raises(BudgetExceededError):
        await router.generate_text("Q4")


@pytest.mark.asyncio
async def test_router_timeout_enforcement() -> None:
    """LLMRouter enforces per-call timeout on slow providers."""
    primary = FakeLLMClient(
        provider_name="gemini",
        latency_seconds=0.2,  # exceeds 0.05s timeout
    )
    router = LLMRouter(primary=primary, max_retries=0)

    with pytest.raises(ProviderUnavailableError):
        await router.generate_text("Slow prompt", timeout=0.05)


@pytest.mark.asyncio
async def test_router_concurrency_limiting() -> None:
    """LLMRouter respects per-provider concurrency limits."""
    active_calls = 0
    max_observed_active = 0
    lock = asyncio.Lock()

    class ConcurrencyTrackingClient(FakeLLMClient):
        async def generate_text(self, prompt: str, **kwargs: Any) -> Any:
            nonlocal active_calls, max_observed_active
            async with lock:
                active_calls += 1
                if active_calls > max_observed_active:
                    max_observed_active = active_calls
            await asyncio.sleep(0.05)
            async with lock:
                active_calls -= 1
            return await super().generate_text(prompt, **kwargs)

    primary = ConcurrencyTrackingClient(provider_name="gemini", canned_text="Answer")
    router = LLMRouter(primary=primary, max_concurrency_per_provider=2)

    # Run 5 concurrent calls
    await asyncio.gather(*(router.generate_text(f"Prompt {i}") for i in range(5)))
    assert max_observed_active <= 2


@pytest.mark.asyncio
async def test_redis_budget_manager() -> None:
    """DailyBudgetManager tracks requests and tokens in Redis."""
    import fakeredis.aioredis

    fake_redis = fakeredis.aioredis.FakeRedis()
    budget = DailyBudgetManager(redis=fake_redis, daily_request_limit=2)

    assert await budget.check_and_increment_request() == 1
    assert await budget.check_and_increment_request() == 2
    with pytest.raises(BudgetExceededError):
        await budget.check_and_increment_request()

    # Record tokens
    await budget.record_tokens(150)
    usage = await budget.get_usage()
    assert usage["tokens"] == 150
    assert usage["requests"] == 3


@pytest.mark.asyncio
async def test_fake_client_queues_and_model_validation() -> None:
    """FakeLLMClient supports queues and different input formats."""
    fake = FakeLLMClient(provider_name="test")
    fake.queue_text("Queued text 1")
    fake.queue_text("Queued text 2")
    assert (await fake.generate_text("p")).content == "Queued text 1"
    assert (await fake.generate_text("p")).content == "Queued text 2"

    # Queue error
    fake.queue_error(RuntimeError("Queued error"))
    with pytest.raises(RuntimeError):
        await fake.generate_text("p")

    # Queue BaseModel instance
    model_inst = SampleQuizQuestion(question="What is 2+2?", options=["3", "4"], correct_option="4")
    fake.queue_json(model_inst)
    res = await fake.generate_json("p", schema=SampleQuizQuestion)
    assert res.parsed == model_inst

    # Queue JSON string
    fake.queue_json('{"question": "What is 3+3?", "options": ["5", "6"], "correct_option": "6"}')
    res2 = await fake.generate_json("p", schema=SampleQuizQuestion)
    assert res2.parsed.correct_option == "6"


@pytest.mark.asyncio
async def test_router_generate_json_and_retry_success() -> None:
    """LLMRouter routes generate_json and recovers from transient error on retry."""
    primary = FakeLLMClient(
        provider_name="gemini",
        scripted_errors=[RuntimeError("Transient 503 error")],
        canned_json={
            "question": "What is capital of Japan?",
            "options": ["Tokyo", "Kyoto"],
            "correct_option": "Tokyo",
        },
    )
    router = LLMRouter(primary=primary, max_retries=1, base_retry_delay_seconds=0.01)

    res = await router.generate_json("Prompt", schema=SampleQuizQuestion)
    assert isinstance(res.parsed, SampleQuizQuestion)
    assert res.parsed.correct_option == "Tokyo"
    assert len(primary.history) == 2  # 1st failed, 2nd succeeded
