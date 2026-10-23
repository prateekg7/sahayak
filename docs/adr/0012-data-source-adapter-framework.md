# 0012 — External Data Source Adapter Framework & Resilience Policies

Status: Accepted
Date: 2026-10-24

## Context

Phase 12 (Local and Civic Info Module) introduces tools that integrate with external public APIs and data sources (transit departures, commodity market prices, government welfare schemes). External APIs are subject to transient latency spikes, rate limits, network failures, upstream outages, and licensing constraints.

Under PRD §5.3, §9.3, §10, and ADR 0010:
1. Voice responses have strict latency targets (p95 $\le 800$ ms) and maximum speech lengths ($\le 300$ characters).
2. Outbound HTTP requests must be strictly allow-listed to eliminate Server-Side Request Forgery (SSRF).
3. The platform must never fail an Alexa+ voice request when valid recent data is available in cache.
4. Upstream data licensing and terms of use require explicit, voice-friendly source attribution.

## Options Considered

1. **Direct HTTP calls inside tool handlers**:
   - *Pros*: Quickest to write initially.
   - *Cons*: Violates PRD §5.2 (tools must be thin adapters), risks unbounded retries, lacks centralized circuit breaking, repeats caching code, and exposes raw upstream errors to voice users.
2. **Unified Data-Source Adapter Framework (`DataSource` port + `BaseHttpDataSource` adapter)**:
   - *Pros*: Centralizes allow-list enforcement, per-source TTL caching, three-state circuit breakers, bounded exponential retries, stale-while-error resilience, and standardized freshness/attribution metadata for both voice summaries and response envelopes.
   - *Cons*: Requires establishing shared base abstractions and mock transports for integration testing.

## Decision

We adopt Option 2: A unified **Data-Source Adapter Framework** in `src/sahayak/modules/local_info/`:
- **`DataSource` Port**: Declares data source identity (`source_id`, `name`, `license`, `attribution`, `default_ttl_seconds`) and retrieval contract.
- **`BaseHttpDataSource`**:
  - Validates all request hostnames against an allow-list before making network calls.
  - Enforces request timeouts (default 2.0s).
  - Implements bounded retries (maximum 2 attempts, exponential backoff with jitter) on idempotent reads only.
  - Integrates a per-source three-state circuit breaker (`CLOSED` $\rightarrow$ `OPEN` after 3 consecutive failures, 30s recovery timeout to `HALF_OPEN`).
  - Implements a **stale-while-error** policy: on upstream error, timeout, or open circuit, cached responses (stored in Redis or in-memory cache) are returned with `is_stale=True` and historical `cached_at` timestamps rather than failing.
- **Attribution & Freshness**: Surfaces plain-speech attribution and freshness prefixes (e.g. "According to Open Transit, as of 5 minutes ago...") and includes structured attribution metadata in the MCP envelope.

## Consequences

- All external adapters in Phase 12 (`transit_status`, `commodity_prices`, `scheme_finder`) extend `BaseHttpDataSource`.
- Outages in external data providers degrade gracefully to cached stale data rather than producing voice error prompts.
- Public tool responses include verified legal attribution and timestamps.
- Upstream testing uses deterministic mock transports without touching the live internet in automated CI runs.
