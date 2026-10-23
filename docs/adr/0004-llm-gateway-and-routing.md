# 0004 — LLM Gateway, Routing, and Provider Abstraction

Status: Accepted
Date: 2026-10-23

## Context

Sahayak requires language model capabilities for quiz question generation, topic summaries, and study planning. Relying on a single LLM provider creates availability risks (rate limits on free/developer tiers, transient outages, latency spikes). Furthermore, directly importing provider SDKs (such as Google GenAI or Groq) in business modules violates domain isolation, complicates testing, and creates vendor lock-in.

Per PRD §13 and §7.6:
1. Feature modules must only interact with a provider-agnostic `LLMClient` port.
2. Structured JSON generation must be strictly validated with Pydantic.
3. Outbound calls must enforce strict timeouts, retries with exponential backoff and jitter, concurrency limits, and circuit breakers.
4. A daily request and token budget must be enforced via Redis to prevent runaway costs or quota exhaustion.
5. Automated tests must run deterministically with zero network calls using a `FakeLLMClient`.

## Options considered

1. **Direct provider SDK usage in feature modules:**
   - *Pros:* Quickest initial prototyping.
   - *Cons:* Heavy coupling to SDKs; untestable without real credentials or network; impossible to implement dynamic fallback or centralized rate limiting.

2. **External LLM proxy service (e.g., LiteLLM proxy, Portkey):**
   - *Pros:* Out-of-the-box routing and dashboard.
   - *Cons:* Adds an extra infrastructure component, network hop, operational overhead, and external dependency for a stateless MCP server.

3. **In-process `LLMClient` port and `LLMRouter` (Selected):**
   - *Pros:* Clean dependency inversion; modular adapters for Gemini and Groq; deterministic `FakeLLMClient` for fast testing; in-process circuit breaker and concurrency limiting; centralized Redis budget tracking.
   - *Cons:* Requires maintaining thin adapter wrappers over provider HTTP/SDK APIs.

## Decision

We adopt an in-process gateway consisting of:
- **`LLMClient` port (`shared/llm/ports.py`):** Abstract protocol defining `generate_text` and `generate_json` returning standardized `LLMResponse` and `TokenUsage`.
- **`FakeLLMClient` (`shared/llm/fake.py`):** Deterministic test fixture with canned responses, call recording, and scripted failure injection.
- **`LLMRouter` (`shared/llm/router.py`):** Routing coordinator that:
  - Manages primary (`GeminiClient`) and fallback (`GroqClient`) providers.
  - Implements three-state circuit breakers (`CLOSED`, `OPEN`, `HALF_OPEN`) per provider.
  - Enforces concurrency limits per provider using asynchronous semaphores.
  - Enforces daily budget checks stored in Redis (`llm:budget:requests:{date}`).
  - Enforces request-level timeouts with `asyncio.timeout`.
  - Records Prometheus metrics (`sahayak_llm_requests_total`, `sahayak_llm_duration_seconds`, `sahayak_llm_tokens_total`).
- Injected into feature modules via `Deps.llm_client`.

## Consequences

- **Positive:** Modules have zero knowledge of Gemini, Groq, or external SDKs. Switching primary and fallback models is a configuration change. Test suites execute in seconds without live API keys.
- **Negative:** Provider-specific prompt peculiarities or parameter differences must be normalized in adapter layers.
- **Reversal:** If an external gateway is ever required, a new adapter implementing `LLMClient` can proxy requests to that gateway without modifying any module.
