# Architecture Decision Records (ADRs) Index

This directory documents the foundational architectural and design decisions for Sahayak.

| ADR | Title | Status | Date | Decision Summary |
|---|---|---|---|---|
| [0001](file:///docs/adr/0001-language-and-framework.md) | Language & Framework | Accepted | 2026-10-23 | Python 3.12, FastAPI, SQLAlchemy 2 (asyncio), PostgreSQL 16, Redis 7. |
| [0002](file:///docs/adr/0002-tool-budget.md) | Tool Budget & Resolution | Accepted | 2026-10-23 | Maximum 6 tools per module (amended for Academics), snapshot verification in CI. |
| [0003](file:///docs/adr/0003-account-linking.md) | Account Linking & Identity | Accepted | 2026-10-23 | OAuth 2.1 authorization code flow with PKCE via AWS Cognito / Auth0. |
| [0004](file:///docs/adr/0004-llm-gateway-and-routing.md) | LLM Gateway & Routing | Accepted | 2026-10-23 | Multi-provider abstraction (Primary: Gemini 2.5 Flash, Fallback: Groq LLaMA 3.3 70B), circuit breaker, daily budget guard. |
| [0009](file:///docs/adr/0009-anonymous-access.md) | Anonymous vs Linked Access | Accepted | 2026-10-23 | Public quizzes and briefs allow anonymous access; personal data (flashcards, study plans, progress) enforces `@requires()`. |
| [0010](file:///docs/adr/0010-latency-and-response-size.md) | Latency & Response Budget | Accepted | 2026-10-23 | Spoken summaries $\le 300$ chars, response payloads $\le 8192$ bytes, p95 latency $\le 800$ ms for deterministic actions. |
| [0011](file:///docs/adr/0011-household-sharing-model.md) | Household Sharing Model | Accepted | 2026-10-23 | Household tenancy (`owner`/`member`), expiring 48h invite codes, mandatory `assert_member` authorization barrier. |
| [0012](file:///docs/adr/0012-data-source-adapter-framework.md) | Data-Source Adapter Framework | Accepted | 2026-10-24 | Unified HTTP data-source adapter with allow-listed hosts, circuit breaker, caching, and stale-while-error policy. |
| [0013](file:///docs/adr/0013-transit-data-source.md) | Transit Data Source & Station Resolution | Accepted | 2026-10-24 | Open GTFS / Open Transit feeds, fuzzy station resolver with colloquial aliases, frequency fallback, anonymous access. |
| [0014](file:///docs/adr/0014-commodity-prices-data-source.md) | Agricultural Commodity Prices & Unit Normalization | Accepted | 2026-10-24 | Agmarknet GODL open data, Hindi/English crop aliasing, quintal-to-kg normalization, freshness guard. |
| [0015](file:///docs/adr/0015-government-scheme-finder.md) | Government Scheme Finder Rules Engine & Curated Dataset | Accepted | 2026-10-24 | Pure code eligibility rules, curated dataset with source links, one-missing-fact clarification, disclaimer. |
| [0016](file:///docs/adr/0016-multi-addon-deployment-profiles.md) | Multi-Add-On Deployment Profiles & Bundle Architecture | Accepted | 2026-10-24 | Four focused add-on bundles (Study, Life, Work, Home) respecting tool budgets with shared identity. |
