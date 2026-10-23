"""Routing, fallback, circuit breaker, and retry orchestration across LLM providers."""

from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from sahayak.core.observability.metrics import (
    LLM_DURATION_SECONDS,
    LLM_REQUESTS_TOTAL,
    LLM_TOKENS_TOTAL,
)
from sahayak.shared.llm.budget import DailyBudgetManager
from sahayak.shared.llm.circuit_breaker import CircuitBreaker
from sahayak.shared.llm.ports import (
    CircuitBreakerOpenError,
    LLMClient,
    LLMError,
    LLMResponse,
    LLMTimeoutError,
    ProviderUnavailableError,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class LLMRouter(LLMClient):
    """Reliable LLM client orchestrating primary and fallback providers.

    Features:
    - Primary and fallback provider resolution
    - Three-state circuit breaker per provider
    - Concurrency limiting via per-provider semaphores
    - Daily request and token quota enforcement via Redis
    - Exponential backoff with jitter on transient failures
    - Prometheus latency and token instrumentation
    """

    def __init__(
        self,
        *,
        primary: LLMClient,
        fallback: LLMClient | None = None,
        budget_manager: DailyBudgetManager | None = None,
        max_concurrency_per_provider: int = 5,
        max_retries: int = 2,
        base_retry_delay_seconds: float = 0.05,
        circuit_breakers: dict[str, CircuitBreaker] | None = None,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.budget_manager = budget_manager or DailyBudgetManager()
        self.max_retries = max_retries
        self.base_retry_delay_seconds = base_retry_delay_seconds

        self._circuit_breakers: dict[str, CircuitBreaker] = circuit_breakers or {
            self.primary.provider_name: CircuitBreaker(self.primary.provider_name),
        }
        if self.fallback is not None and self.fallback.provider_name not in self._circuit_breakers:
            self._circuit_breakers[self.fallback.provider_name] = CircuitBreaker(
                self.fallback.provider_name
            )

        self._semaphores: dict[str, asyncio.Semaphore] = {
            self.primary.provider_name: asyncio.Semaphore(max_concurrency_per_provider),
        }
        if self.fallback is not None:
            self._semaphores[self.fallback.provider_name] = asyncio.Semaphore(
                max_concurrency_per_provider
            )

    @property
    def provider_name(self) -> str:
        return "router"

    def get_circuit_breaker(self, provider: str) -> CircuitBreaker:
        """Return the circuit breaker tracking the given provider."""
        if provider not in self._circuit_breakers:
            self._circuit_breakers[provider] = CircuitBreaker(provider)
        return self._circuit_breakers[provider]

    async def _execute_with_provider(
        self,
        client: LLMClient,
        call_type: str,
        prompt: str,
        schema: type[BaseModel] | dict[str, Any] | None,
        model: str | None,
        temperature: float,
        max_tokens: int,
        timeout: float,
    ) -> LLMResponse:
        """Execute a call on a single provider with concurrency limit and retries."""
        provider = client.provider_name
        cb = self.get_circuit_breaker(provider)
        cb.can_execute()

        semaphore = self._semaphores.setdefault(provider, asyncio.Semaphore(5))
        last_exception: Exception | None = None

        for attempt in range(self.max_retries + 1):
            start_time = time.monotonic()
            try:
                async with semaphore:
                    async with asyncio.timeout(timeout):
                        if call_type == "json":
                            if schema is None:
                                raise ValueError("schema must be provided for json calls")
                            response = await client.generate_json(
                                prompt=prompt,
                                schema=schema,
                                model=model,
                                temperature=temperature,
                                max_tokens=max_tokens,
                                timeout=timeout,
                            )
                        else:
                            response = await client.generate_text(
                                prompt=prompt,
                                model=model,
                                temperature=temperature,
                                max_tokens=max_tokens,
                                timeout=timeout,
                            )

                elapsed = time.monotonic() - start_time
                cb.record_success()

                # Telemetry
                used_model = response.model or model or "default"
                LLM_REQUESTS_TOTAL.labels(
                    provider=provider, model=used_model, outcome="success"
                ).inc()
                LLM_DURATION_SECONDS.labels(provider=provider, model=used_model).observe(elapsed)
                LLM_TOKENS_TOTAL.labels(
                    provider=provider, model=used_model, token_type="prompt"
                ).inc(response.usage.prompt_tokens)
                LLM_TOKENS_TOTAL.labels(
                    provider=provider, model=used_model, token_type="completion"
                ).inc(response.usage.completion_tokens)
                LLM_TOKENS_TOTAL.labels(
                    provider=provider, model=used_model, token_type="total"
                ).inc(response.usage.total_tokens)

                await self.budget_manager.record_tokens(response.usage.total_tokens)
                return response

            except TimeoutError:
                last_exception = LLMTimeoutError(
                    detail=f"Provider {provider} timed out after {timeout}s"
                )
                logger.warning(
                    "LLM provider %s timed out attempt %s/%s",
                    provider,
                    attempt + 1,
                    self.max_retries + 1,
                )
            except Exception as exc:
                last_exception = exc
                logger.warning(
                    "LLM provider %s error on attempt %s/%s: %s",
                    provider,
                    attempt + 1,
                    self.max_retries + 1,
                    exc,
                )

            # Check if we should retry
            if attempt < self.max_retries:
                jitter = random.uniform(0.01, 0.05)  # noqa: S311
                delay = (self.base_retry_delay_seconds * (2**attempt)) + jitter
                await asyncio.sleep(delay)

        # Retries exhausted
        cb.record_failure()
        used_model = model or "default"
        LLM_REQUESTS_TOTAL.labels(provider=provider, model=used_model, outcome="failure").inc()
        if isinstance(last_exception, LLMError):
            raise last_exception
        attempts = self.max_retries + 1
        detail_msg = f"Provider {provider} failed after {attempts} attempts: {last_exception}"
        raise ProviderUnavailableError(detail=detail_msg) from last_exception

    async def _route(
        self,
        call_type: str,
        prompt: str,
        schema: type[BaseModel] | dict[str, Any] | None,
        model: str | None,
        temperature: float,
        max_tokens: int,
        timeout: float,
    ) -> LLMResponse:
        """Enforce budget and route between primary and fallback."""
        # 1. Budget check
        await self.budget_manager.check_and_increment_request()

        # 2. Try primary provider
        primary_failed = False
        try:
            return await self._execute_with_provider(
                self.primary,
                call_type=call_type,
                prompt=prompt,
                schema=schema,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )
        except (CircuitBreakerOpenError, ProviderUnavailableError, LLMTimeoutError) as exc:
            logger.warning(
                "Primary LLM provider %s failed (%s); checking fallback",
                self.primary.provider_name,
                exc,
            )
            primary_failed = True
        except Exception:
            logger.exception(
                "Unexpected error in primary LLM provider %s", self.primary.provider_name
            )
            primary_failed = True

        # 3. Fallback provider if available
        if primary_failed and self.fallback is not None:
            logger.info(
                "Invoking fallback LLM provider %s",
                self.fallback.provider_name,
            )
            try:
                response = await self._execute_with_provider(
                    self.fallback,
                    call_type=call_type,
                    prompt=prompt,
                    schema=schema,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=timeout,
                )
                LLM_REQUESTS_TOTAL.labels(
                    provider=self.fallback.provider_name,
                    model=model or "default",
                    outcome="fallback_routed",
                ).inc()
                return response
            except Exception as fallback_exc:
                logger.error(
                    "Fallback LLM provider %s also failed: %s",
                    self.fallback.provider_name,
                    fallback_exc,
                )
                both_fail_detail = (
                    f"Both primary ({self.primary.provider_name}) and "
                    f"fallback ({self.fallback.provider_name}) LLM providers failed"
                )
                raise ProviderUnavailableError(detail=both_fail_detail) from fallback_exc

        no_fallback_detail = (
            f"Primary LLM provider {self.primary.provider_name} failed and no fallback available"
        )
        raise ProviderUnavailableError(detail=no_fallback_detail)

    async def generate_text(
        self,
        prompt: str,
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        timeout: float = 8.0,
    ) -> LLMResponse:
        return await self._route(
            call_type="text",
            prompt=prompt,
            schema=None,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
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
        return await self._route(
            call_type="json",
            prompt=prompt,
            schema=schema,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )
