# PRD: Sahayak — a Modular Voice Assistant Platform for Alexa+ (MCP)

> Working name: **Sahayak** (Hindi for "helper"). The name is a config value, not hard-coded.
> Document status: v1.0 Production Release, Certified and Reconciled. Owner: product owner (the user).
> Final Architecture: 10 functional modules + settings, 33 public MCP tools, 4 Alexa+ add-on deployment profiles (ADR 0016).

---

## 0. How the building agent must use this document

1. **This is a production product, not a prototype.** Everything below (tests, CI, observability, security, migrations, docs) is in scope from the first commit. Do not skip "later" items marked as required for a milestone.
2. **Do not invent Alexa+ facts.** Section 3 separates *verified facts* from *items to verify*. Before building anything that depends on an "items to verify" row, read the linked official doc and record the finding in `docs/adr/` as an ADR. If the docs contradict this PRD, **the docs win** and the PRD must be updated in the same commit.
3. **Work milestone by milestone** (Section 21). Each milestone has acceptance criteria; a milestone is done only when all are met in CI.
4. **Respect the module boundaries** in Section 7 and 8. They are what make the system easy to extend. Boundary violations fail CI (import-linter).
5. **Keep decisions in writing.** Any decision that deviates from this PRD, or fills a gap, gets a short ADR (`docs/adr/NNNN-title.md`).
6. **Ask the owner only for what cannot be discovered**: credentials, domain name, Alexa+ Private Preview access, cloud account. Everything else, decide, document, and proceed.

---

## 1. Product overview

### 1.1 Vision
A modular, always-available voice assistant platform delivered as Alexa+ MCP add-ons behind one account and shared memory. Fully implemented and production-ready across 10 domains: Academics, Productivity, Personal Finance, Health & Wellness, Career Development, Home & Family Logistics, Small Business Bookkeeping, Language Acquisition, Local & Civic Information, and User Settings/Preferences. Deployed via 4 specialized Alexa+ add-ons (`study`, `life`, `work`, `home`) to maintain optimal NLU routing within Alexa+'s tool sweet spot (ADR 0016).

### 1.2 How it works (mental model)
- **Alexa+ is the AI and the client.** It understands speech, decides which tool to call, and phrases and speaks results.
- **Our server is an MCP server** exposing tools over **Streamable HTTP**. It runs deterministic business logic, stores state, and (where needed) calls an LLM *internally* to generate content such as quiz questions.
- Alexa+ talks to us through an **Alexa+ MCP add-on** that we register with the Alexa AI CLI.

```
User ──voice──▶ Alexa+ (NLU, tool choice, speech)
                  │  MCP over Streamable HTTP (JSON-RPC 2.0)
                  ▼
          Alexa+ MCP add-on (bridge, registered by us)
                  │
                  ▼
        ┌──────── Sahayak MCP server (this product) ────────┐
        │  Core: transport, auth, rate limit, observability │
        │  Modules: academics | productivity | finance | …  │
        │  Shared: users, events, LLM gateway, cache        │
        └────────┬─────────────┬───────────────┬────────────┘
                 ▼             ▼               ▼
            PostgreSQL        Redis        LLM providers
                                           (Gemini / Groq / …)
```

### 1.3 Goals
- G1. Fully working, certifiable Alexa+ MCP add-on, with Academics as the first module.
- G2. Any-topic quiz generation that is fast (voice-friendly), cheap (cached), and factually grounded.
- G3. Adding a new module requires **only adding a folder** plus one line in config; the core never changes.
- G4. Horizontally scalable, stateless application tier; clear path to split modules into separate services.
- G5. Production-grade engineering: typed, tested, observable, secure, reproducible deployments.

### 1.4 Non-goals (v1)
- No mobile or web client of our own (a minimal read-only web dashboard is a stretch goal, not required).
- No custom speech recognition or text-to-speech; Alexa+ owns the voice layer.
- No payments or real financial transactions; the finance module is a *ledger*, not a bank integration.
- No medical advice; the health module (future) logs data only.

### 1.5 Success metrics
| Metric | Target |
|---|---|
| Tool-call success rate (non-5xx, schema-valid) | ≥ 99.5% |
| p95 latency, non-generating tool calls (server-side) | ≤ 800 ms |
| p95 latency, `quiz_start` on cache hit | ≤ 1.0 s |
| p95 latency, `quiz_start` on cache miss | ≤ 5 s (with prefetch strategy in §10.3) |
| Quiz question validity (passes automated + sampled human check) | ≥ 98% |
| Alexa+ certification | Passed before public launch |
| Test coverage (line, core + modules) | ≥ 85%, branch coverage tracked |

> Latency targets are internal budgets. Alexa+'s real timeout and response-size limits are **items to verify** (§3.2).

---

## 2. Users and key scenarios

**Primary persona: the student / self-learner** (school, college, competitive exams, upskilling). Secondary personas appear as modules are added (professional, household manager, shop owner).

### 2.1 Voice dialogs (acceptance reference)
**Quiz**
- "Alexa, ask Sahayak to quiz me on photosynthesis." → `quiz_start`
- "Carbon dioxide." / "Option B." → `quiz_answer`
- "How am I doing?" → `progress_report`
- "Quiz me on my weak topics." → `quiz_start` with `source=weak_topics`

**Flashcards**
- "Add a flashcard: capital of Australia is Canberra." → `flashcards(action=add)`
- "Review my flashcards." → `flashcards(action=review_next)` then `grade`

**Study plan**
- "My chemistry exam is on the 15th. Make a study plan." → `study_plan(action=create)`
- "What should I study today?" → `study_plan(action=today)`

**Brief**
- "Give me a quick brief on the French Revolution." → `topic_brief`

### 2.2 Voice UX rules (apply to every tool)
- Return a short `spoken_summary` (target ≤ 300 characters, hard cap in config) that is natural to read aloud, in addition to structured data. Alexa+ phrases the final speech, but a good summary steers it well.
- One question at a time. Never return lists longer than 5 items for speech; put the rest in structured data.
- Never put the correct answer in the *question* response.
- Errors are conversational: tell the user what to do next ("I don't have an active quiz. Want me to start one?").
- Numbers, dates, and units must be unambiguous when spoken (ISO dates in data; human dates in `spoken_summary`).

---

## 3. Alexa+ integration: verified facts and items to verify

### 3.1 Verified from Amazon's developer docs (as of Oct 2026)
- Alexa+ acts as the **MCP client**. You return standard MCP responses; Alexa+ handles language understanding, response generation, and UI rendering.
- Supported MCP spec version: **2025-11-25**. Transport: **Streamable HTTP**. A server using the legacy **SSE transport must migrate** before connecting.
- You make your server available by creating an **Alexa+ MCP add-on** (a bridge that handles tool discovery and protocol translation). Alexa+ keeps an **add-on registry** that indexes your registered capabilities.
- Tooling: the **Alexa AI CLI** (`alexa-ai configure`, `alexa-ai new mcp ...`, `alexa-ai deploy`) and an **Add-on Agent Skill** (prompt: "Help me create an Alexa+ add-on.") that scaffolds the add-on, derives `shortDescription`, `fullDescription`, `examplePhrases` from the MCP server, and submits for certification after web-simulator testing.
- **Tool changes require a redeploy** (`alexa-ai deploy`) for Alexa+ to see them.
- Alexa+ also supports the **MCP Apps extension** (interactive UI via `resourceUri`); without it, Alexa+ renders data-only visuals from the tool response.
- Sessions are based on the customer's **previous conversations with Alexa+**, not an explicit session identifier from our server. **Our tools must therefore be stateless with respect to transport and carry their own IDs** (e.g., `quiz_id`).
- If the customer is **account-linked**, the server can personalize results.
- Testing ladder: **MCP Inspector**, **Alexa+ Add-on Local Inspector**, **Web Simulator** (multi-turn, no device needed), or a physical device.
- Access is **Private Preview**: onboarding requires approval and credentials.
- Docs home: https://developer.amazon.com/docs/alexaplus/add-ons/home
  Overview: https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-overview
  Quickstart: https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-quickstart.html
  Local Inspector: https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-local-inspector
  Web Simulator: https://developer.amazon.com/docs/alexaplus/add-ons/test-with-web-simulator.html
  Client lifecycle: https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-client-lifecycle.html

### 3.2 Items to verify before depending on them (write an ADR for each)
| # | Question | Why it matters | Default assumption until verified |
|---|---|---|---|
| V1 | Max number of tools / tool-description length Alexa+ handles well | Tool-set design (§9) | ≤ 15 tools total at launch, ≤ 4 per module |
| V2 | Tool-call timeout and max response size | Generation strategy, payload caps | Verified sub-500 ms round-trip requirement; 8 KB response cap remains an ASSUMPTION |
| V3 | Account Linking (MCP) exact flow, required OAuth endpoints, scopes, token format | Auth (§12) | Verified OAuth 2.1 authorization-code + PKCE S256, refresh tokens, protected-resource metadata, bearer tokens; no `WWW-Authenticate` on 401 |
| V4 | Supported locales for MCP add-ons (en-US, en-IN, hi-IN?) | Content language | en-US first |
| V5 | Certification guidelines (content, privacy policy, example phrases, error handling) | Release checklist | Privacy policy URL, support contact required |
| V6 | Elicitation support details | Optional multi-turn parameter gathering | Do not depend on it in v1 |
| V7 | Whether Alexa+ calls `tools/list` per request or caches until redeploy | Tool-schema change process | Verified: redeploy after tool/resource changes |
| V8 | Whether anonymous (unlinked) users can invoke tools | Auth policy (§12.3) | Verified: account linking is optional; persistent tools require linking by product policy |
| V9 | Origin / auth headers Alexa+ sends to our endpoint | Origin validation and allow-listing | Verified bearer token via `Authorization`; validate `Origin` if present (docs silent on its value) |

---

## 4. Functional requirements

### 4.1 Platform (all modules)
- FR-P1. Expose one MCP endpoint (`/mcp`) implementing MCP 2025-11-25 over Streamable HTTP, **stateless** (no server-side transport sessions).
- FR-P2. Auto-register tools from enabled modules at startup; modules enabled via configuration.
- FR-P3. Unified user identity across modules (linked-account subject → internal `user_id`).
- FR-P4. Per-user data export and deletion (privacy requirement), exposed via an admin/CLI path and a documented process.
- FR-P5. Feature flags per module and per tool.
- FR-P6. Health, readiness, and metrics endpoints.
- FR-P7. Standard result envelope (§9.3) and error model (§9.4) for every tool.

### 4.2 Academics module (v1 scope, detailed in §10)
- FR-A1. Start a quiz on **any topic** with chosen difficulty and length; questions are LLM-generated, grounded in retrieved source text, validated, cached.
- FR-A2. Answer questions by letter, option text, or number; tolerant matching.
- FR-A3. Score, explanations, per-topic accuracy history.
- FR-A4. Flashcards with spaced repetition (SM-2).
- FR-A5. Study plan from exam date and topics, with "what should I study today".
- FR-A6. Progress reports: weak topics, streaks, weekly summary.
- FR-A7. Topic brief: concise, sourced overview.

### 4.3 Future modules (roadmap, not v1; the platform must make them cheap to add)
Productivity (tasks, habits, notes, focus timer), Finance (expense ledger, budgets, bill splits, reminders), Health (water/meal/workout logs), Career (mock interviews, application tracker), Home/Family (shared lists, chores), Small Business (orders, dues, daily sales), Language Learning (vocab, practice), Local/Civic info (data-source dependent). Each follows the same module contract (§8).

---

## 5. Architecture

### 5.1 Style: modular monolith, hexagonal inside each module
One deployable application, internally split into **modules with strict boundaries**. This gives the speed and simplicity of a monolith with a clean path to extract a module into its own MCP server later (§20).

Layers inside every module (dependencies point inward only):
```
tools (MCP adapters)  →  service (use cases)  →  domain (entities, rules)
                                  ↓
                  ports (interfaces: repository, llm, clock, …)
                                  ↑
               adapters (SQLAlchemy repo, LLM provider, HTTP clients)
```

### 5.2 Rules (enforced by import-linter in CI)
1. A module may import `core` and `shared`, **never another module's internals**.
2. Cross-module collaboration happens only through (a) a module's published `api.py` (a small typed interface) or (b) domain events via the outbox (§11.4).
3. Each module owns its own **Postgres schema** (`academics.*`, `finance.*`, …) and its own Alembic migration branch. No cross-schema joins in application code.
4. `core` knows nothing about any specific module.
5. Tools are thin: parse/validate input → call service → map to result envelope. No business logic in tool functions.

### 5.3 Runtime topology
- **App tier**: N stateless replicas of the FastAPI + MCP server behind a load balancer (TLS terminated at the LB).
- **Worker tier**: background jobs (question prefetch, spaced-repetition reminders, cleanup) on a Redis-backed queue.
- **Data**: PostgreSQL (primary + optional read replica), Redis (cache, rate limits, queue, short-lived locks).
- **External**: LLM providers, Wikipedia/Wikimedia REST API (grounding), identity provider (account linking).

---

## 6. Technology stack

| Concern | Choice | Rationale |
|---|---|---|
| Language | **Python 3.12** | Strong MCP SDK, rich LLM ecosystem, fast iteration |
| MCP | Official **`mcp` Python SDK** (FastMCP, Streamable HTTP, `stateless_http=True`, `json_response=True`) | Spec-compliant; stateless matches Alexa+ session model. Pin the version; confirm the 2025-11-25 spec support in release notes |
| Web framework | **FastAPI** + Uvicorn (Gunicorn workers in prod) | Async, typed, OpenAPI for non-MCP endpoints |
| Validation | **Pydantic v2** | Tool schemas are generated from models |
| ORM / DB | **SQLAlchemy 2.x (async)** + **asyncpg**, **Alembic** migrations | Mature; per-module migration branches |
| Database | **PostgreSQL 16** | JSONB for questions/options, schemas per module |
| Cache / queue | **Redis 7**, **arq** (async jobs) | Simple, lightweight workers |
| LLM access | Provider-agnostic `LLMClient` port; adapters for **Google Gemini (Flash)** (default) and **Groq** (fallback); official SDKs | Free-tier friendly, swappable. Model names live in config only |
| HTTP client | **httpx** (async) with retries/timeouts | Wikipedia, IdP JWKS, providers |
| Auth | OAuth 2.1 **resource server**; JWT validation via JWKS (**authlib** or **PyJWT**); external IdP (Amazon Cognito or Auth0, ADR to decide) | Don't build an authorization server in v1 |
| Config | **pydantic-settings**, 12-factor env vars | One typed config object |
| Logging | **structlog** (JSON) | Correlation IDs |
| Metrics/Tracing | **OpenTelemetry** (traces + metrics), **Prometheus** exposition; Sentry optional | Vendor-neutral |
| Testing | **pytest**, pytest-asyncio, **testcontainers** (Postgres/Redis), **respx** (HTTP mocks), **hypothesis** (property tests), MCP SDK client for contract tests | See §17 |
| Quality | **ruff** (lint+format), **mypy --strict**, **import-linter**, **pre-commit**, **bandit**, **pip-audit** | Enforced in CI |
| Packaging | **uv** (lockfile, reproducible installs), `pyproject.toml` | Fast, deterministic |
| Containers | Multi-stage **Docker**, non-root user, **docker compose** for local | Parity with prod |
| IaC | **Terraform** (AWS: ECS Fargate, RDS Postgres, ElastiCache, ALB, ACM, Secrets Manager, CloudWatch) | Same cloud as Alexa; reproducible |
| CI/CD | **GitHub Actions** | Lint, type-check, test, build, scan, deploy |
| Local tunnel | **cloudflared** | Expose local server to Alexa+ during dev |
| Low-cost profile | Same container on Cloud Run / Fly.io / Render with managed Postgres | For free-tier or hobby deployments; documented in `docs/deploy/low-cost.md` |

> If the owner prefers TypeScript, an equivalent stack (official TS MCP SDK, Fastify, Drizzle/Prisma, Vitest) is acceptable, but record it as an ADR before starting. Do not mix languages.

---

## 7. Repository structure

```
sahayak/
├── pyproject.toml            # deps, tool config (ruff, mypy, pytest, import-linter)
├── uv.lock
├── Makefile                  # make dev | test | lint | typecheck | migrate | run | tunnel
├── Dockerfile                # multi-stage, non-root
├── docker-compose.yml        # app, worker, postgres, redis
├── .env.example
├── .pre-commit-config.yaml
├── .github/workflows/        # ci.yml, release.yml, security.yml
├── infra/terraform/          # modules: network, db, cache, app, secrets, observability
├── docs/
│   ├── PRD.md                # this file
│   ├── adr/                  # architecture decision records
│   ├── alexa/                # add-on config, certification checklist, test scripts
│   ├── runbooks/             # incident, deploy, rollback, key rotation
│   └── deploy/low-cost.md
├── alexa/                    # add-on project generated/maintained by alexa-ai CLI
├── src/sahayak/
│   ├── main.py               # app factory: build FastAPI, mount MCP, lifespan
│   ├── core/
│   │   ├── config.py         # pydantic-settings
│   │   ├── mcp_server.py     # FastMCP instance, module registration
│   │   ├── module.py         # Module protocol + registry (§8)
│   │   ├── profiles.py       # Deployment profiles & add-on bundles (ADR 0016)
│   │   ├── flags.py          # FeatureFlagStore, @check_feature_flag, UserPreferenceService
│   │   ├── auth/             # JWT validation, principal, scopes, protected-resource metadata
│   │   ├── db/               # engine, session, base, unit-of-work
│   │   ├── cache.py          # Redis wrapper
│   │   ├── ratelimit.py
│   │   ├── errors.py         # error types → MCP error mapping
│   │   ├── envelope.py       # result envelope (§9.3)
│   │   ├── events.py         # outbox + dispatcher
│   │   ├── observability/    # logging, tracing, metrics, request-id middleware
│   │   └── security/         # origin validation, headers, input limits
│   ├── shared/
│   │   ├── users/            # user + identity models/services (platform-level)
│   │   ├── llm/              # LLMClient port, gemini.py, groq.py, fake.py, router.py
│   │   ├── content/          # wikipedia.py grounding client, sanitizer
│   │   ├── srs/              # Spaced repetition scheduling (sm2.py)
│   │   └── time.py           # Clock port
│   ├── modules/
│   │   ├── academics/        # 6 tools: quiz_start, quiz_answer, flashcards, study_plan, progress_report, topic_brief
│   │   ├── productivity/     # 6 tools: tasks, habits, notes, focus_timer, daily_briefing, weekly_review
│   │   ├── finance/          # 4 tools: expense_log, budget, split_bill, finance_report
│   │   ├── health/           # 2 tools: health_log, health_summary
│   │   ├── career/           # 3 tools: interview_practice, application_tracker, career_practice
│   │   ├── home/             # 3 tools: shared_list, chores, pantry_recipes
│   │   ├── business/         # 3 tools: orders, ledger, sales_summary
│   │   ├── language/         # 2 tools: vocab, language_practice
│   │   ├── local_info/       # 3 tools: transit_status, commodity_prices, scheme_finder
│   │   ├── settings/         # 1 tool: settings (assistant controls)
│   │   └── _template/        # copy-me skeleton for new modules (kept compiling in CI)
│   └── worker.py             # arq worker entry
├── scripts/                  # admin.py, export_user.py, delete_user.py, seed.py, snapshot_tools.py
└── tests/
    ├── unit/  integration/  contract/  security/  fixtures/
    └── snapshots/            # tools.json, study_tools.json, life_tools.json, work_tools.json, home_tools.json
```

---

## 8. Module contract (the scalability mechanism)

Every module implements:

```python
# core/module.py
from typing import Protocol, runtime_checkable
from mcp.server.fastmcp import FastMCP

@runtime_checkable
class Module(Protocol):
    name: str                      # "academics"
    version: str                   # semver of the module's tool surface
    def register_tools(self, mcp: FastMCP, deps: "Deps") -> None: ...
    def register_jobs(self, worker: "WorkerRegistry") -> None: ...
    def migrations_path(self) -> str | None: ...      # Alembic branch
    def health(self) -> "HealthStatus": ...           # dependency health checks
    def on_event(self, event: "DomainEvent") -> None: ...   # event subscriptions
    async def export_user_data(self, user_id: str) -> dict[str, Any]: ...  # GDPR Right to Access
    async def delete_user_data(self, user_id: str) -> None: ...             # GDPR Right to Erasure
```

- **Discovery & Bundles**: Handled via `core/profiles.py` and `DEPLOYMENT_PROFILE` or `ENABLED_MODULES` config.
- **Dependencies (`Deps`)** are injected: DB session factory, cache, LLM client, clock, event bus, current-principal accessor. Modules never construct infrastructure themselves.
- **Tool-count budget**: Solved via ADR 0016 by grouping modules into 4 targeted Alexa+ add-on profiles:
  - `study`: 6 tools ($\le 6$ budget)
  - `life`: 12 tools ($\le 12$ budget)
  - `work`: 6 tools ($\le 8$ budget)
  - `home`: 8 tools ($\le 10$ budget)
  - `full`: 33 tools ($\le 35$ monolith budget)

---

## 9. MCP server design

### 9.1 Transport and endpoints
| Path | Purpose |
|---|---|
| `POST /mcp` | MCP Streamable HTTP endpoint (JSON-RPC 2.0). Responses as JSON (`json_response=True`) unless streaming is needed |
| `GET /mcp` | Return `405` if server-initiated SSE streams are not used (per spec) |
| `GET /.well-known/oauth-protected-resource` | OAuth protected-resource metadata (RFC 9728) pointing to the authorization server (verify V3) |
| `GET /healthz` | Liveness (process up) |
| `GET /readyz` | Readiness (DB + Redis reachable) |
| `GET /metrics` | Prometheus; **not public** (internal network or auth) |

- **Stateless mode**: no per-client in-memory session. Any replica serves any request.
- Validate `Origin` when present (DNS-rebinding protection per MCP spec); allow-list in config.
- Protocol version negotiation handled by the SDK; add a contract test asserting `2025-11-25` is negotiated.
- Request size limit (e.g., 64 KB), a configurable per-request deadline within the verified sub-500 ms round-trip budget, and graceful cancellation.

### 9.2 Tool design rules
1. **Few, flexible tools per module** (≤ 4), named `<noun>_<verb>` or a single noun with an `action` enum. Names are stable public API.
2. **Descriptions say when to use *and when not to*** and include one example utterance. This drives Alexa+'s tool selection more than anything else.
3. **Inputs are small and forgiving**: enums for known choices, sensible defaults, no free-form JSON blobs.
4. **Every response carries its own state handle** (`quiz_id`, `card_id`, `plan_id`) because the transport is stateless and Alexa+ has no server session ID.
5. **Idempotency**: mutating tools accept an optional `request_id`; repeated calls with the same ID return the original result.
6. **Schema stability**: `tests/snapshots/tools.json` is generated from `tools/list`; any change fails CI until the snapshot is intentionally updated. Remember tool changes require `alexa-ai deploy`.
7. **Read-only vs mutating** tools are annotated using MCP tool annotations where supported.

### 9.3 Result envelope
Every tool returns MCP `content` (a concise text rendering) plus `structuredContent` conforming to:

```json
{
  "ok": true,
  "spoken_summary": "Question 1 of 5. Which gas do plants absorb for photosynthesis?",
  "data": { "...tool-specific..." },
  "next_actions": ["answer the question", "ask for a hint"],
  "meta": { "request_id": "01J...", "module": "academics", "version": "1.0.0" }
}
```
- `spoken_summary` ≤ `SPOKEN_SUMMARY_MAX_CHARS` (default 300).
- Total response ≤ `MAX_RESPONSE_BYTES` (default 8192), enforced by a serializer guard and tested.

### 9.4 Error model
Errors map to a stable set; tool failures return `isError: true` with the envelope `ok=false`:

| Code | Meaning | Spoken guidance example |
|---|---|---|
| `invalid_input` | Schema or semantic validation failed | "I didn't catch the topic. What would you like to be quizzed on?" |
| `not_found` | ID unknown/expired | "I can't find that quiz. Want to start a new one?" |
| `auth_required` | Needs a linked account | "Link your account in the Alexa app to save your progress." |
| `rate_limited` | Throttled | "Let's slow down for a moment and try again shortly." |
| `upstream_unavailable` | LLM/Wikipedia failure after retries/fallback | "I'm having trouble generating questions. Try another topic or try again soon." |
| `internal` | Unexpected | "Something went wrong on my side." (details only in logs) |

Never leak stack traces, SQL, provider names, or secrets to the client.

---

## 10. Academics module specification

### 10.1 Tools (4 tools + 1 optional, within the budget)

**1. `quiz_start`**
- Use when the user asks to be quizzed. Do not use to answer a question in an active quiz.
- Input: `topic: str` (1–120 chars) | `source: enum["topic","weak_topics","due_review"] = "topic"`, `difficulty: enum["easy","medium","hard"] = "medium"`, `num_questions: int 3–10 = 5`, `request_id?: str`
- Output `data`: `{quiz_id, number, total, question, options: [{key:"A", text}, ...]}`. **Never includes the correct answer.**

**2. `quiz_answer`**
- Use when the user answers the current quiz question (by letter, number, or text).
- Input: `quiz_id: str`, `answer: str`, `request_id?: str`
- Output `data`: `{correct: bool, correct_key, explanation, score: {correct, answered, total}, next: {number, question, options} | null, finished: bool, summary?}`
- Answer matching (domain layer, deterministic): normalize case/punctuation; accept letter (A–D), ordinal ("second"), exact option text, fuzzy match above threshold (rapidfuzz, config); ambiguous input returns `invalid_input` asking for clarification, without consuming an attempt.

**3. `flashcards`** — `action: enum["add","review_next","grade","list_due"]`
- `add`: `front`, `back`, `deck?`. `review_next`: returns next due card front. `grade`: `card_id`, `rating: enum["again","hard","good","easy"]` (SM-2 scheduling). `list_due`: count and next few.
- Requires linked account for persistence (`auth_required` otherwise).

**4. `study_plan`** — `action: enum["create","today","update","list"]`
- `create`: `goal`, `exam_date` (ISO), `topics: list[str]`, `hours_per_day?`. Produces a day-by-day plan using deterministic scheduling (LLM only suggests topic breakdown; scheduling is code). `today`: today's tasks.

**5. `progress_report`** — `scope: enum["summary","weak_topics","streak","weekly"]`; and optional **`topic_brief`** — `topic`, `length: enum["short","medium"] = "short"` (grounded in Wikipedia text; includes source attribution in `data.sources`).
> Count check: quiz_start, quiz_answer, flashcards, study_plan, progress_report = 5. That exceeds the default per-module cap of 4. **Resolve in M0 by ADR**: either (a) merge `quiz_start`/`quiz_answer` into a single `quiz(action=…)` tool, or (b) raise the per-module cap after verifying V1. Default recommendation: keep separate quiz tools (clearer for voice), merge `progress_report` + `topic_brief` into `learning_insights(kind=…)` if the cap is enforced.

### 10.2 Domain rules
- **Scoring**: 1 point per correct; hints (future) reduce nothing in v1. Quiz finishes after N answered questions or on explicit end.
- **Session lifecycle**: `active → finished | expired` (expire after `QUIZ_TTL_MINUTES`, default 120). Expired quizzes return `not_found` with a restart prompt.
- **Weak topics**: topic accuracy over the last K attempts (K configurable) below threshold.
- **SM-2** implemented as a pure function with property tests.
- **Anonymous quizzes**: allowed (owner `NULL`); `quiz_id` is an unguessable ULID/UUIDv4; progress and weak-topic features require a linked account.

### 10.3 Quiz generation pipeline (scalable content strategy)

```
topic ──▶ normalize ──▶ cache lookup (topic_key, difficulty, lang)
                          │ hit ──────────────────────────────▶ serve
                          ▼ miss
                   retrieve source text (Wikipedia REST; fallback: LLM-only with flag)
                          ▼
                   LLM generate N+buffer MCQs as strict JSON
                          ▼
                   validate (schema, 4 distinct options, exactly 1 correct,
                             stem ≤ limit, no answer leakage in stem, dedupe by hash)
                          ▼
                   (optional) verification pass: second prompt/model answers the
                   question from the source; discard on disagreement
                          ▼
                   persist to question bank (status=approved|flagged) ──▶ serve
```
- **Normalization**: lowercase, strip punctuation, collapse whitespace, simple synonym/alias table; topic stored with `topic_key` (slug) and display name. Optional embedding-based topic merging is a later enhancement (ADR).
- **Latency strategy**: on a miss, generate a **first batch of 5** synchronously within the time budget; enqueue a background job to expand the bank and prefetch for the likely next difficulty. While the user answers question *k*, the next question is already stored, so later turns are cache reads.
- **Question bank growth**: every approved question is reusable across users, so cost scales with distinct topics, not users.
- **Serving**: select unseen questions for the user (or random for anonymous) with stratified difficulty.
- **Prompt-injection defense**: retrieved text is untrusted data; wrap in delimiters, instruct the model to ignore instructions inside it, validate output strictly, never execute or follow links.
- **Quality feedback loop**: store `flag_count`; a future tool/admin path can flag bad questions; questions with high flags are quarantined.
- **Prompt versioning**: prompts live in `prompts/` with a version string saved on each generated question for traceability.
- **Fallback chain**: primary provider → secondary provider → serve from nearest cached topic/difficulty → `upstream_unavailable`.

### 10.4 Future modules (sketch for roadmap alignment)
| Module | Candidate tools | Notes |
|---|---|---|
| productivity | `tasks(action)`, `habits(action)`, `notes(action)`, `focus_timer(action)` | Habits feed academics streaks via events |
| finance | `expense_log`, `budget`, `split_bill`, `finance_report` | Decimal money types, currency in config, no bank integrations |
| health | `health_log(kind)`, `health_summary` | Logging only; no medical advice |
| career | `interview_practice`, `application_tracker` | Reuses LLM gateway |
| home | `shared_list`, `chores` | Multi-user households need an ADR (sharing model) |
| business | `orders`, `ledger`, `sales_summary` | Multi-tenant considerations |

---

## 11. Data model

### 11.1 Platform schema (`core`)
- `users(id uuid pk, created_at, deleted_at null, locale, timezone)`
- `user_identities(id, user_id fk, issuer, subject, created_at, unique(issuer, subject))`
- `outbox_events(id, aggregate, type, payload jsonb, created_at, processed_at null)`
- `idempotency_keys(key, user_id null, tool, response jsonb, created_at, expires_at)`
- `audit_log(id, user_id null, action, resource, ip_hash, created_at)` (no sensitive payloads)

### 11.2 Academics schema (`academics`)
- `topics(id, topic_key unique, display_name, created_at)`
- `questions(id uuid, topic_id fk, difficulty, stem text, options jsonb, correct_key char(1), explanation text, source_url null, source_hash, content_hash unique, prompt_version, model, status enum(approved,flagged,quarantined), flag_count, created_at)`
- `quizzes(id uuid pk, user_id null, topic_id, difficulty, total, current_index, status, score_correct, created_at, expires_at, finished_at null)`
- `quiz_questions(quiz_id, position, question_id, answered_at null, selected_key null, is_correct null, primary key(quiz_id, position))`
- `decks(id, user_id, name)`; `cards(id, deck_id, user_id, front, back, ease, interval_days, repetitions, due_at, created_at)`
- `study_plans(id, user_id, goal, exam_date, created_at)`; `plan_tasks(id, plan_id, date, topic, minutes, done_at null)`
- `topic_stats(user_id, topic_id, attempts, correct, last_attempt_at, primary key(user_id, topic_id))`

Indexes: `questions(topic_id, difficulty, status)`, `cards(user_id, due_at)`, `quizzes(user_id, status)`, `plan_tasks(plan_id, date)`.

### 11.3 Conventions
- UUIDv7/ULID primary keys, `timestamptz` UTC everywhere, soft delete only where required, constraints in the DB (not only in code), explicit migrations (no autogenerate without review), **expand/contract** migration style for zero-downtime deploys.

### 11.4 Events (cross-module)
Transactional outbox → dispatcher → module `on_event`. Initial events: `quiz.finished`, `flashcard.graded`, `habit.completed` (future), `expense.logged` (future). Handlers must be idempotent.

---

## 12. Authentication, account linking, authorization

### 12.1 Design
- Our server is an **OAuth 2.1 resource server**. Authorization (login, consent, token issuance) is delegated to an **external identity provider** chosen by ADR (Amazon Cognito or Auth0 recommended). We do **not** store passwords.
- Access tokens are validated as JWTs: signature via cached JWKS, `iss`, `aud`, `exp`, `nbf`, scope checks. Clock skew tolerance ≤ 60 s. Alexa+ MCP account linking sends bearer tokens in the `Authorization` header.
- The `sub` claim maps to an internal `user_id` through `user_identities` (auto-provision on first valid token).
- Expose RFC 9728 protected-resource metadata and return a `401` or `403` without `WWW-Authenticate` when linking is required, as required by the MCP account-linking integration.
- **Exact Alexa+ account-linking flow, endpoints, and scopes must be taken from the "Account Linking (MCP)" doc (V3).** Implement to that doc.

### 12.2 Scopes (initial)
`academics.read`, `academics.write`; one pair per future module. Tools declare required scope; the core enforces it before dispatch.

### 12.3 Anonymous access policy
Unlinked users may use stateless/ephemeral features (quiz without history, topic brief). Persistent features return `auth_required` with a spoken instruction to link in the Alexa app (V8).

### 12.4 Authorization
Every repository query is scoped by `user_id` from the verified principal, never from tool input. A test suite asserts cross-user access is impossible for every tool.

---

## 13. LLM gateway

- `LLMClient` port: `generate_json(prompt, schema, *, temperature, max_tokens, timeout) -> dict` and `generate_text(...)`.
- Adapters: `GeminiClient` (default, Flash-class model), `GroqClient` (fallback), `FakeClient` (tests, deterministic fixtures).
- Model names, temperature, and per-provider rate limits come from config. **Do not hard-code model IDs**; free-tier limits and model names change often. Read current limits from provider docs at implementation time.
- `Router` handles retries with jitter, circuit breaker, provider fallback, per-provider concurrency limits, and a global token/request budget per day (`LLM_DAILY_BUDGET`) to prevent runaway cost.
- Structured output: use provider-native JSON/schema mode where available; always re-validate with Pydantic.
- Free-tier caveat: provider terms may allow use of prompts for product improvement. **Never send user PII to a free-tier provider.** Quiz generation sends only topic + public source text.
- Log token usage and cost estimates per call (metrics), never prompt contents that include user data.

---

## 14. Security and privacy

- **Transport**: TLS 1.2+ only (HSTS), terminated at the load balancer; HTTP → HTTPS redirect.
- **MCP-specific**: validate `Origin`; bind to localhost only in dev; reject oversized bodies; strict JSON-RPC parsing.
- **Input handling**: Pydantic validation on every tool; length limits; reject control characters; output encoding where text is echoed.
- **Rate limiting**: per principal (or per IP when anonymous) with Redis sliding window; separate tighter limits on generation paths.
- **Secrets**: env vars from AWS Secrets Manager (prod); never committed; `.env.example` only; secret scanning in CI (gitleaks); key rotation runbook.
- **Dependencies**: `pip-audit`, Dependabot/Renovate, pinned lockfile, SBOM generation in release, container scan (Trivy).
- **Data protection**: encryption at rest (RDS/ElastiCache), encrypted backups, least-privilege DB roles (app role cannot run DDL), no PII in logs (hash IPs, never log tokens).
- **Privacy**: minimal data collection; published privacy policy (certification, V5); `scripts/export_user.py` and `delete_user.py` implement access and erasure; retention policy for quizzes/audit logs configured and tested.
- **Threat model** documented in `docs/security/threat-model.md` (STRIDE) covering: forged tool calls, token theft/replay, prompt injection via retrieved content, SSRF (only allow-listed outbound hosts), enumeration of IDs, cost-abuse of LLM paths.
- **Outbound allow-list**: HTTP client only talks to configured hosts (Wikipedia, IdP, LLM providers).

---

## 15. Observability and operations

- **Logs**: structured JSON, fields: `ts, level, request_id, trace_id, user_id (internal), module, tool, latency_ms, outcome`.
- **Metrics**: tool call count/latency/error by tool and module; LLM calls/tokens/cost/failures by provider; cache hit ratio; DB pool saturation; queue depth; question-validation reject rate.
- **Tracing**: OpenTelemetry spans per request → tool → service → DB/LLM/HTTP.
- **Dashboards and alerts** (as code in `infra/`): error rate > 1% for 5 min, p95 latency over budget, LLM fallback rate spike, queue backlog, DB connections > 80%, certificate expiry.
- **SLOs**: availability 99.9% monthly for `/mcp`; error budget policy in runbooks.
- **Runbooks**: deploy, rollback, DB restore, rotate secrets, provider outage, Alexa+ add-on redeploy.
- **Backups**: automated daily + PITR; restore drill each quarter.

---

## 16. Non-functional requirements

| Area | Requirement |
|---|---|
| Scalability | Stateless app; scale horizontally on CPU/latency; target 100 RPS per small instance pair without code changes |
| Availability | ≥ 2 replicas across AZs in prod; zero-downtime deploys (rolling) |
| Performance | See §1.5; DB queries p95 ≤ 50 ms; no N+1 (tested with query-count assertions) |
| Reliability | Timeouts on every outbound call; retries only for idempotent operations; circuit breakers |
| Maintainability | mypy strict, ruff clean, ≤ 400-line modules by convention, docstrings on public interfaces |
| Portability | Runs from a single Docker image; config only via env |
| Accessibility of speech | Spoken summaries free of symbols/markdown; tested with a lint rule |
| i18n | Strings and prompts keyed by locale; en-US at launch, structure ready for en-IN/hi-IN (V4) |
| Compliance | Privacy policy, data deletion, no child-directed-content assumptions without legal review |

---

## 17. Testing strategy

| Level | What | Tools |
|---|---|---|
| Unit | Domain logic (SM-2, scoring, answer matching, validators), services with fake ports | pytest, hypothesis |
| Integration | Repositories vs real Postgres, Redis, migrations up/down, outbox dispatch | testcontainers |
| Contract | Boot the app, use the MCP SDK **client** over Streamable HTTP: `initialize` → `tools/list` → `tools/call`; assert protocol version `2025-11-25`, schemas, envelope, error model, snapshot of `tools/list` | pytest + `mcp` client |
| LLM pipeline | `FakeClient` fixtures: valid, malformed, injection-laden, duplicate, wrong-answer outputs; assert validator rejections and fallback chain | pytest, respx |
| Security | Cross-user access tests per tool, token validation matrix (expired, wrong aud/iss, bad sig), origin rejection, rate-limit behavior | pytest |
| Performance | Load test of `/mcp` with `quiz_answer` and cache-hit `quiz_start` | k6 or Locust (scheduled) |
| E2E (manual + scripted) | MCP Inspector, Local Inspector, Web Simulator scripts in `docs/alexa/test-plans.md` | Amazon tools |

CI gates: ruff, mypy, import-linter, unit + integration + contract tests, coverage ≥ 85%, snapshot check, bandit, pip-audit, gitleaks, Docker build + Trivy scan, migration check (upgrade→downgrade→upgrade on a clean DB).

---

## 18. CI/CD and environments

- **Environments**: `local` (compose), `staging` (mirrors prod, used for Alexa+ Web Simulator testing), `prod`.
- **Source-control workflow**: direct-to-trunk on `main`; one completed subtask per Conventional Commit; no feature branches or pull requests; ADR required for architectural changes.
- **Pipeline**: direct commit to `main` → CI gates → build image (tag = git SHA) → deploy to staging → smoke tests (MCP contract suite against staging URL) → manual approval → prod rolling deploy → post-deploy smoke test → automatic rollback on failed health checks.
- **Migrations**: run as a separate release step before app rollout; expand/contract only.
- **Versioning**: semver for the product; each module carries its own tool-surface version in `meta`.
- **Alexa+ add-on deploy** (`alexa-ai deploy`) is a separate, explicit pipeline step triggered **only when the tool snapshot changes**, with a checklist in `docs/alexa/release-checklist.md`.

---

## 19. Connecting to Alexa+ (step-by-step)

> Prerequisite: Alexa+ for Builders **Private Preview** access (approval + developer account). Until approved, complete steps 1–3 and use the community bridge only as an unofficial demo aid.

1. **Build and run the server locally**: `make dev` (compose up; app at `http://localhost:8000/mcp`).
2. **Test with MCP Inspector** (standard MCP tool): connect via Streamable HTTP, list tools, call each with valid and invalid inputs, verify the envelope and errors.
3. **Expose publicly for development**: `make tunnel` (cloudflared) → `https://<random>.trycloudflare.com/mcp`. For staging/prod, use a stable HTTPS domain with a valid certificate.
4. **Install and sign in to the Alexa AI CLI**: `alexa-ai configure` (follow current install docs from the Quickstart page).
5. **Create the add-on** — either path:
   - *Path A (recommended)*: in a supported coding agent, use the **Add-on Agent Skill** with the prompt "Help me create an Alexa+ add-on." It connects to the MCP server, discovers tools, proposes a name, and generates `shortDescription`, `fullDescription`, `examplePhrases`. **Review and edit the generated copy** (see §19.1).
   - *Path B (manual)*:
     ```
     alexa-ai new mcp --name "Sahayak" --locale en-US --mcp-server-url "https://<your-domain>/mcp"
     alexa-ai deploy
     ```
     On success the CLI returns an **Add-on ID and version**. The add-on manifest contains an integration entry of type `MCP` with the server `uri`.
6. **Configure account linking** per the MCP account-linking doc (V3): register Alexa+ as an allowed client/redirect in the IdP, configure scopes, set token audience to our resource identifier, and fill linking details in the add-on config.
7. **Test in the Local Inspector** (UI widget rendering, readiness report) and then the **Web Simulator** (multi-turn quiz, error paths, unlinked vs linked). Capture results in `docs/alexa/test-plans.md`.
8. **Test on a physical Alexa+ device** (route sessions from the simulator or per the "Test Your MCP Add-ons" doc).
9. **Submit for certification** (via the Agent Skill or console) after meeting the certification guidelines (V5): privacy policy URL, support contact, accurate descriptions, example phrases that actually work, graceful error handling.
10. **After any tool change**: update the snapshot, run contract tests, deploy server, then `alexa-ai deploy`, then re-run the simulator smoke script.

### 19.1 Add-on listing content (draft; refine after V4/V5)
- **Short description**: "Quiz yourself on any topic, review flashcards, and plan your study time."
- **Example phrases** (must be verified to route correctly in the simulator):
  - "Quiz me on photosynthesis."
  - "Review my flashcards."
  - "Make a study plan for my chemistry exam on the 15th."
  - "How am I doing in my quizzes?"
  - "Give me a quick brief on the French Revolution."

### 19.2 Local developer commands (Makefile)
```
make setup      # uv sync, pre-commit install
make dev        # docker compose up (app, worker, postgres, redis)
make migrate    # alembic upgrade heads
make test       # unit + integration + contract
make lint       # ruff + mypy + import-linter
make snapshot   # regenerate tests/snapshots/tools.json (intentional change only)
make tunnel     # cloudflared tunnel --url http://localhost:8000
make inspector  # launch MCP Inspector against local server
```

---

## 20. Scalability path (what changes as it grows)

| Stage | Trigger | Action | Code change needed |
|---|---|---|---|
| 1. Single deployment | Launch | 2+ replicas, 1 worker, managed Postgres/Redis | None |
| 2. Scale out | CPU/latency | Add replicas; add Postgres read replica for reporting queries; tune pools | Config only (read-replica session factory already abstracted) |
| 3. Content scale | Many topics | Pre-generation jobs for popular topics; embedding-based topic merging; moderation queue | Job + adapter additions inside academics |
| 4. Tool-count pressure (V1) | Too many tools for Alexa+ | Per-user module enablement, or split into **multiple add-ons**, each a separate MCP server | **Extract module**: run `ENABLED_MODULES=finance` as its own deployment from the same codebase; module already owns its schema and API |
| 5. Team scale | Multiple squads | Modules become separate repos/services; events move from DB outbox to a broker (SQS/SNS or Kafka) | Swap event bus adapter; module contracts unchanged |

Design choices that keep this cheap: stateless app, per-module Postgres schemas, published module APIs, outbox events, config-driven module enablement, provider-agnostic LLM port.

---

## 21. Milestones and acceptance criteria

**M0 — Foundation (platform skeleton)**
- Repo, CI, Docker, compose, pre-commit, ADR template, import-linter contracts.
- App factory, config, logging, request IDs, health/readiness, DB/Redis wiring, migrations framework.
- MCP endpoint (stateless Streamable HTTP) with a `ping_echo` test tool in `_template`; contract test passes via MCP SDK client; MCP Inspector connects.
- ADRs written for: V1 outcome (tool budget), IdP choice, language/stack confirmation.
- **Done when**: CI green, `make dev` works from a clean clone, staging deploy reachable over HTTPS.

**M1 — Identity and security baseline**
- JWT validation, principal, scopes, protected-resource metadata, origin validation, rate limiting, error envelope, idempotency keys.
- Account linking configured per V3 against the IdP; security tests (token matrix, cross-user).
- **Done when**: a linked token reaches a test tool as a verified principal; unauthenticated call to a protected tool returns the proper challenge/`auth_required`.

**M2 — Academics: quiz**
- LLM gateway (Gemini + Groq + Fake), Wikipedia grounding, generation pipeline, question bank, `quiz_start`, `quiz_answer`, answer matching, scoring, TTL, anonymous mode, background prefetch.
- **Done when**: contract + pipeline tests pass; p95 budgets met on staging; Web Simulator can complete a 5-question quiz and shows correct multi-turn behavior; validity sampling of 100 generated questions ≥ 98% acceptable.

**M3 — Academics: flashcards, planner, progress**
- `flashcards`, `study_plan`, `progress_report`/`topic_brief` (per the §10.1 tool-count ADR), SM-2, weak-topic logic, events (`quiz.finished` → stats).
- **Done when**: all FR-A1–A7 demonstrated in the simulator; data export/delete scripts verified.

**M4 — Hardening and certification**
- Threat model reviewed, load test, dashboards/alerts, runbooks, backup/restore drill, privacy policy, add-on listing copy, certification checklist complete; physical-device test.
- **Done when**: certification submitted and passed; SLO dashboards live; no open high-severity findings.

**M5 — Productivity module** (proves the extension model)
- Built from `_template` without modifying `core/`; adds tasks, habits, notes, focus timer, daily morning briefing, and weekly review; habit completion consumed by academics streak logic.
- **Done when**: all 6 tools operational, tool snapshot updated, and privacy hooks implemented.

**M6 — Extended Modules & Release Readiness (Phases 6–13)**
- **Finance (Phase 6)**: `expense_log`, `budget`, `split_bill`, `finance_report`.
- **Health (Phase 7)**: `health_log`, `health_summary`.
- **Career (Phase 8)**: `interview_practice`, `application_tracker`, `career_practice`.
- **Home & Family (Phase 9)**: `shared_list`, `chores`, `pantry_recipes` (ADR 0011 household tenancy).
- **Small Business (Phase 10)**: `orders`, `ledger`, `sales_summary` (atomic stock decrements).
- **Language Learning (Phase 11)**: `vocab`, `language_practice` (SM-2 reviews, multi-turn chat).
- **Local & Civic Information (Phase 12)**: `transit_status`, `commodity_prices`, `scheme_finder`.
- **Multi-Add-On Scaling & Release (Phase 13)**: Deployment bundles (`study`, `life`, `work`, `home`, `full`), `weekly_review`, feature flags, user preferences, admin CLI (`scripts/admin.py`), and v1.0.0 release readiness.
- **Done when**: all 33 tools pass contract and isolation suites, all 5 profile snapshots match, and release artifacts generated.

---

## 22. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Private Preview access delayed | Blocks real-device testing | Build to spec, test with Inspector, optionally use the community bridge for demos only |
| Alexa+ limits (tools, timeout, size) lower than assumed | Redesign of tools/latency | V1/V2 verification in M0; budgets enforced by tests; prefetch design |
| LLM free-tier limits or terms change | Generation outages/cost | Provider abstraction, caching, fallback chain, daily budget, no PII to providers |
| Incorrect quiz answers | Trust damage | Grounding, verification pass, flag/quarantine loop, sampled QA |
| Spec/SDK drift | Breakage | Pin versions, contract tests on protocol version, Renovate with CI |
| Tool surface changes need redeploy | Release friction | Snapshot test + explicit release checklist |
| Prompt injection via retrieved text | Bad content | Delimiting, strict validation, allow-listed sources, no tool execution from content |
| Account-linking complexity | Delays | Delegate to IdP, follow doc exactly, isolate in `core/auth` |

---

## 23. Open questions for the product owner
1. Domain name for the public endpoint (needed for TLS and add-on config).
2. Cloud choice: AWS (default in this PRD) or a low-cost platform for the first release?
3. Preferred IdP: Amazon Cognito or Auth0?
4. Target launch locale(s): en-US only, or en-IN as well?
5. Is a legal entity/privacy-policy owner available for certification?
6. Brand name: keep "Sahayak" or change (config + listing copy only).

---

## 24. Appendix

### 24.1 Environment variables (`.env.example`)
```
APP_ENV=local|staging|prod
APP_NAME=Sahayak
PUBLIC_BASE_URL=https://example.com
ENABLED_MODULES=academics
DATABASE_URL=postgresql+asyncpg://sahayak:sahayak@postgres:5432/sahayak
REDIS_URL=redis://redis:6379/0
ALLOWED_ORIGINS=
MAX_TOOLS=15
MAX_TOOLS_PER_MODULE=4
SPOKEN_SUMMARY_MAX_CHARS=300
MAX_RESPONSE_BYTES=8192
REQUEST_TIMEOUT_SECONDS=8
RATE_LIMIT_PER_MINUTE=60
RATE_LIMIT_GENERATION_PER_MINUTE=10
OIDC_ISSUER=
OIDC_AUDIENCE=
OIDC_JWKS_URL=
LLM_PRIMARY_PROVIDER=gemini
LLM_FALLBACK_PROVIDER=groq
LLM_PRIMARY_MODEL=          # set from provider docs at implementation time
LLM_FALLBACK_MODEL=         # set from provider docs at implementation time
GEMINI_API_KEY=
GROQ_API_KEY=
LLM_DAILY_BUDGET_REQUESTS=1000
QUIZ_TTL_MINUTES=120
OTEL_EXPORTER_OTLP_ENDPOINT=
SENTRY_DSN=
```

### 24.2 Reference snippet: stateless MCP server wiring
```python
# core/mcp_server.py  (confirm API against the pinned SDK version)
from mcp.server.fastmcp import FastMCP

def build_mcp(settings) -> FastMCP:
    return FastMCP(
        settings.app_name.lower(),
        stateless_http=True,   # no server-side transport session
        json_response=True,    # plain JSON responses
    )

# main.py
# app = FastAPI(lifespan=lifespan)       # lifespan must run the MCP session manager
# app.mount("/", mcp.streamable_http_app())   # exposes /mcp
```

### 24.3 Reference snippet: thin tool + envelope
```python
@mcp.tool(description=(
    "Start a multiple-choice quiz on a topic. Use when the user asks to be "
    "quizzed (e.g. 'quiz me on photosynthesis'). Do not use to answer a question "
    "in an active quiz; use quiz_answer for that."))
async def quiz_start(topic: str, difficulty: Difficulty = "medium",
                     num_questions: int = 5, request_id: str | None = None):
    principal = deps.current_principal()          # may be anonymous
    result = await deps.academics.start_quiz(principal, topic, difficulty,
                                             num_questions, request_id)
    return envelope.ok(result.data, spoken=result.spoken)   # enforces size caps
```

### 24.4 Definition of Done (every commit)
- Types, lint, import boundaries clean; tests added/updated; coverage not reduced.
- Tool snapshot updated **only** if the public tool surface changed intentionally, with release-checklist note.
- Migrations reversible and reviewed; no breaking schema change without expand/contract plan.
- Logs/metrics added for new paths; no PII in logs.
- Docs/ADR updated; PRD updated if requirements changed.

### 24.5 ADR index (completed and accepted)
0001 Language and framework · 0002 Tool-count budget · 0003 Account linking and identity · 0004 LLM gateway and routing · 0009 Anonymous vs linked access · 0010 Latency and response size budget · 0011 Household sharing model · 0012 Data-source adapter framework · 0013 Transit data source and station resolution · 0014 Agricultural commodity prices and unit normalization · 0015 Government scheme finder rules engine · 0016 Multi-add-on deployment profiles and bundle architecture
