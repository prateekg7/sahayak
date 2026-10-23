# tasks.md — Sahayak: End-to-End Implementation Plan

Companion to `PRD.md`. The PRD says *what and why*; this file says *what to do next*, in small steps.

---

## How to use this file

- **Work top to bottom.** Each task lists its dependencies; never start a task before its dependencies are done.
- **One task = one commit.** Each is sized at **roughly 150–1,500 lines of code including tests** (the "Est. LOC" line). If you find a task growing past 2,000 lines, stop and split it.
- Tick the box in the heading when the task's **Done when** conditions all pass in CI.
- Every task automatically inherits the PRD's **Definition of Done** (§24.4): types, lint, import boundaries, tests, no PII in logs, docs/ADR updated.
- Tool names, schemas, and rules come from PRD §9–§10. If a task conflicts with the PRD, update both in the same commit and write an ADR.
- Tasks marked **[VERIFY]** depend on facts about Alexa+ or external services that must be checked in official docs first (PRD §3.2). Do not guess.

### Prompt template to hand a task to an AI coding agent
```
Read PRD.md fully, then implement task <ID> from tasks.md only.
Follow the module boundaries and Definition of Done in the PRD.
Do not modify files outside the task's listed scope unless required; if required, explain why.
Write the tests listed under "Done when". Run `make lint test` and fix failures before finishing.
```

### Phase overview
| Phase | Theme | Tasks |
|---|---|---|
| 0 | Foundation and platform skeleton | T0.1–T0.13 |
| 1 | Identity, security, events | T1.1–T1.9 |
| 2 | Shared services (LLM, grounding, jobs) | T2.1–T2.5 |
| 3 | Academics module (quiz, flashcards, planner, progress, brief) | T3.1–T3.15 |
| 4 | Infrastructure, Alexa+ integration, hardening, certification | T4.1–T4.10 |
| 5 | Productivity module | T5.1–T5.5 |
| 6 | Finance module | T6.1–T6.4 |
| 7 | Health module | T7.1–T7.2 |
| 8 | Career module | T8.1–T8.3 |
| 9 | Home and family module | T9.1–T9.3 |
| 10 | Small business module | T10.1–T10.3 |
| 11 | Language learning module | T11.1–T11.2 |
| 12 | Local and civic info module | T12.1–T12.4 |
| 13 | Multi-add-on scaling, cross-module features, v1.0 release | T13.1–T13.4 |

> **Recommended launch scope:** finish Phases 0–4 and certify the academics add-on first. Phases 5–12 are independent modules you can ship in any order; each proves that the platform needs **no core changes**.

---

# PHASE 0 — Foundation and platform skeleton

### [x] T0.1 — Repository scaffold and developer tooling
- **Depends on:** none · **Est. LOC:** ~250
- **What it does:** Creates the repo layout from PRD §7 so every later task has a home, and sets up the tools that keep code quality high from the first commit.
- **Implement:** `pyproject.toml` (Python 3.12, deps, ruff/mypy/pytest/import-linter config), `uv.lock`, `Makefile` targets (`setup, dev, test, lint, typecheck, migrate, snapshot, tunnel, inspector`), `.pre-commit-config.yaml` (ruff, mypy, gitleaks), `.gitignore`, `.env.example`, empty package folders with `__init__.py`, `docs/adr/0000-template.md`, `docs/adr/0001-language-and-framework.md`, `README.md` stub.
- **Done when:** `make setup && make lint` passes on a clean clone; pre-commit hooks run; the directory tree matches PRD §7.

### [x] T0.2 — Typed configuration
- **Depends on:** T0.1 · **Est. LOC:** ~250
- **What it does:** One validated settings object that the whole app reads; invalid config stops startup immediately (fail fast).
- **Implement:** `core/config.py` with `pydantic-settings` (all variables from PRD §24.1), environment profiles (`local/staging/prod`), secret-typed fields, validation (e.g., `ENABLED_MODULES` not empty, URLs valid), `get_settings()` cached accessor.
- **Done when:** unit tests cover defaults, overrides, and invalid values; secrets never appear in `repr()`.

### [x] T0.3 — Docker image and local compose stack
- **Depends on:** T0.2 · **Est. LOC:** ~150
- **What it does:** One command brings up app, worker, Postgres, and Redis identical to production topology.
- **Implement:** multi-stage `Dockerfile` (uv install, non-root user, healthcheck), `docker-compose.yml` (app, worker, postgres:16, redis:7, volumes, env file), `make dev`, `make tunnel` (cloudflared).
- **Done when:** `make dev` starts all services; `curl localhost:8000/healthz` works once T0.5 lands; image runs as non-root; image size reviewed.

### [x] T0.4 — Continuous integration pipeline
- **Depends on:** T0.1 · **Est. LOC:** ~200 (YAML)
- **What it does:** Every commit is automatically checked so quality gates are enforced by machines, not memory.
- **Implement:** `.github/workflows/ci.yml` jobs: lint (ruff), types (mypy strict), import-linter, tests with Postgres/Redis service containers, coverage gate (≥ 85%), bandit, pip-audit, gitleaks, Docker build + Trivy scan. `security.yml` scheduled weekly. Dependabot/Renovate config.
- **Done when:** a commit with a deliberate lint error fails; a clean commit passes; caches make CI under ~6 minutes.

### [x] T0.5 — Application factory, health endpoints, request IDs
- **Depends on:** T0.2 · **Est. LOC:** ~300
- **What it does:** Builds the FastAPI app, assigns each request a correlation ID, and exposes liveness/readiness.
- **Implement:** `main.py` app factory + lifespan hooks, request-ID middleware (accept inbound ID or generate ULID, add to logs and response header), `/healthz` (always 200 if process up), `/readyz` (checks DB + Redis once those exist; pluggable checks list), global exception handler returning safe errors.
- **Done when:** tests assert request ID propagation, readiness fails when a dependency check fails, and unhandled exceptions return no stack trace.

### [x] T0.6 — Database layer and migrations framework
- **Depends on:** T0.2, T0.3 · **Est. LOC:** ~500
- **What it does:** Async database access with clean transactions, and migrations that can be owned per module.
- **Implement:** `core/db/` (async engine, session factory, declarative `Base` with naming conventions, **Unit-of-Work** helper), Alembic setup with **branch labels per module** and a `core` branch creating schema `core`, `make migrate`, migration check script (upgrade → downgrade → upgrade), least-privilege role notes in docs, testcontainers fixture for Postgres.
- **Done when:** integration test migrates a clean DB, rolls back, and re-applies; UoW commits/rolls back correctly under exceptions.

### [x] T0.7 — Redis wrapper and rate limiter
- **Depends on:** T0.2 · **Est. LOC:** ~350
- **What it does:** Shared cache access and a sliding-window rate limiter used by tools and generation paths.
- **Implement:** `core/cache.py` (namespaced keys, JSON get/set with TTL, distributed lock helper), `core/ratelimit.py` (sliding window, keyed by principal or IP hash, separate named limits), unit tests with fakeredis plus one integration test.
- **Done when:** limiter blocks the (N+1)th call in a window, resets after the window, and is atomic under concurrent calls.

### [x] T0.8 — Result envelope and error model
- **Depends on:** T0.2 · **Est. LOC:** ~350
- **What it does:** Guarantees every tool returns the same shape and every failure maps to a stable, voice-friendly error.
- **Implement:** `core/envelope.py` (`ok()`, `fail()`, size guard for `MAX_RESPONSE_BYTES`, `spoken_summary` length guard, meta with request ID/module/version), `core/errors.py` (exception hierarchy mapped to PRD §9.4 codes), spoken-summary linter (no markdown/symbols).
- **Done when:** unit tests for truncation, size cap, error-code mapping, and "no internals leaked" assertions pass.

### [x] T0.9 — Module protocol, registry, template module, boundary rules
- **Depends on:** T0.5, T0.8 · **Est. LOC:** ~450
- **What it does:** The extension mechanism: modules plug in via config, and import rules keep them isolated.
- **Implement:** `core/module.py` (`Module` protocol, `Deps` container, `ModuleRegistry` that loads `ENABLED_MODULES`, fails loudly on unknown), `modules/_template/` (complete skeleton incl. a sample tool, service, repo port, migration branch), import-linter contracts (modules ↛ other modules; core ↛ modules; domain ↛ adapters), CI test that the template compiles.
- **Done when:** enabling the template registers its tool; an illegal cross-module import fails `make lint`.

### [x] T0.10 — MCP server wiring (stateless Streamable HTTP)
- **Depends on:** T0.9 · **Est. LOC:** ~400
- **What it does:** Exposes `/mcp` as a spec-compliant endpoint that Alexa+ (and MCP Inspector) can connect to, with no server-side session state.
- **Implement:** `core/mcp_server.py` (FastMCP with `stateless_http=True`, `json_response=True`), mounting into FastAPI with correct lifespan, tool registration via the registry, `GET /mcp` behavior per spec (405 when no SSE), per-request timeout and cancellation, the `ping_echo` tool in the template module.
- **Done when:** MCP Inspector connects and lists/calls `ping_echo`; the SDK client negotiates protocol `2025-11-25` in a test; two app replicas behind round-robin both answer correctly.

### [x] T0.11 — Contract test harness, tool snapshot, tool-budget guard
- **Depends on:** T0.10 · **Est. LOC:** ~350
- **What it does:** Protects the public tool surface (changing it requires an Alexa+ redeploy) and enforces the tool-count budget.
- **Implement:** `tests/contract/` using the MCP client over HTTP (`initialize → tools/list → tools/call`), `scripts/snapshot_tools.py` writing `tests/snapshots/tools.json`, snapshot comparison test, budget test (`MAX_TOOLS`, `MAX_TOOLS_PER_MODULE`), description-lint test (each description must contain a "use when" and example phrase).
- **Done when:** modifying a tool schema without updating the snapshot fails CI; exceeding the budget fails CI.

### [x] T0.12 — Observability foundation
- **Depends on:** T0.5 · **Est. LOC:** ~450
- **What it does:** Makes behavior visible: structured logs, metrics, and traces tied to requests and tools.
- **Implement:** `core/observability/` — structlog JSON config with redaction (tokens, emails), OpenTelemetry tracing setup (HTTP, DB, httpx), Prometheus metrics (tool calls/latency/errors, cache hits, LLM counters registered but unused), tool-call instrumentation wrapper, `/metrics` protected by internal-network or token config.
- **Done when:** a tool call emits a log line with `request_id, tool, latency_ms, outcome`, a span tree, and metric increments; redaction test passes.

### [x] T0.13 — [VERIFY] Alexa+ documentation research and ADRs
- **Depends on:** none (start in parallel with T0.1) · **Est. LOC:** docs only
- **What it does:** Resolves every unknown in PRD §3.2 so later tasks build on facts.
- **Implement:** read the official docs linked in PRD §3.1 (plus MCP account-linking, certification guidelines, supported locales, tool limits, timeouts, elicitation, anonymous access); write ADRs 0002 (tool budget, V1), 0003 (account linking, V3), 0009 (anonymous vs linked, V8), 0010 (timeout/size, V2), plus notes for V4–V7 and V9 in `docs/alexa/findings.md`; update PRD defaults that turned out wrong; apply for **Alexa+ Private Preview** access if not yet approved.
- **Done when:** every row V1–V9 has a written answer or an explicit "docs silent, default assumption kept" note with a risk entry.

---

# PHASE 1 — Identity, security, events

### [x] T1.1 — Platform user model
- **Depends on:** T0.6 · **Est. LOC:** ~300
- **What it does:** Gives every linked person one internal `user_id`, independent of which IdP they signed in with.
- **Implement:** `shared/users/` models (`users`, `user_identities` with unique `(issuer, subject)`), repo + service (`get_or_create_by_identity`, soft delete), migration in `core` branch, locale/timezone fields.
- **Done when:** integration tests show idempotent provisioning under concurrent first-requests (unique-constraint race handled).

### [x] T1.2 — JWT validation and JWKS cache
- **Depends on:** T0.2, T0.7 · **Est. LOC:** ~400
- **What it does:** Verifies that a bearer token really came from our identity provider and is meant for us.
- **Implement:** `core/auth/jwt.py` — JWKS fetch with caching and key rotation handling, validation of signature, `iss`, `aud`, `exp`, `nbf`, 60 s skew, algorithm allow-list (no `none`), clear exception types.
- **Done when:** test matrix passes: valid, expired, wrong audience, wrong issuer, bad signature, unknown `kid`, rotated key, malformed token.

### [x] T1.3 — Principal, scopes, tool authorization, protected-resource metadata
- **Depends on:** T1.1, T1.2, T0.10 · **Est. LOC:** ~500
- **What it does:** Turns a verified token into a `Principal` that tools can use, and enforces required scopes before a tool runs.
- **Implement:** `core/auth/principal.py` (`Principal` with `user_id|None`, scopes, anonymous flag), HTTP middleware extracting the bearer token (token optional because anonymous access is allowed per T0.13 outcome), tool decorator `@requires(scope=...)` / `@allow_anonymous`, `/.well-known/oauth-protected-resource` (RFC 9728), correct `401` + `WWW-Authenticate` challenge, `auth_required` spoken error mapping. **Follow ADR 0003 exactly.**
- **Done when:** protected tool without token → `auth_required`; with token missing scope → forbidden; anonymous-allowed tool works with no token; metadata endpoint validates against the ADR.

### [x] T1.4 — HTTP security hardening
- **Depends on:** T0.10 · **Est. LOC:** ~300
- **What it does:** Closes common web attack paths on the public MCP endpoint.
- **Implement:** `Origin` validation (allow-list, DNS-rebinding protection), request body size limit, security headers (HSTS, no-sniff, etc.), strict JSON-RPC parse errors, global and per-route timeouts, outbound HTTP allow-list helper for `httpx`.
- **Done when:** tests show bad origin rejected, oversized body rejected, outbound call to a non-allow-listed host blocked.

### [x] T1.5 — Idempotency for mutating tools
- **Depends on:** T0.6, T0.8 · **Est. LOC:** ~300
- **What it does:** Prevents duplicate effects when Alexa+ or a retry repeats the same call.
- **Implement:** `idempotency_keys` table + migration, `@idempotent` wrapper using `request_id` (scoped per user/tool), stores the first response with TTL, returns it on replay, concurrency-safe via unique constraint/advisory lock.
- **Done when:** replaying the same `request_id` returns the identical result and creates no second row; different users cannot collide.

### [x] T1.6 — Domain events and transactional outbox
- **Depends on:** T0.6, T0.9 · **Est. LOC:** ~450
- **What it does:** Lets modules react to each other's activity without importing each other (e.g., a finished quiz updates stats).
- **Implement:** `outbox_events` table, `core/events.py` (`publish()` inside the caller's transaction, dispatcher loop in the worker, at-least-once delivery, retry with backoff, dead-letter table), module subscription registration through `Module.on_event`, idempotent-handler test helper.
- **Done when:** an event published in a rolled-back transaction is never delivered; a handler failure retries then dead-letters; duplicate delivery is harmless in the sample handler.

### [x] T1.7 — Identity provider setup and account-linking configuration **[VERIFY]**
- **Depends on:** T0.13, T1.3 · **Est. LOC:** ~300 (Terraform/config + docs)
- **What it does:** Creates the actual login system Alexa+ will redirect users to.
- **Implement:** IdP chosen in ADR 0003 (Cognito or Auth0) as code under `infra/terraform/idp/` (user pool/tenant, app client for Alexa+, redirect URIs, scopes `academics.read/write`, token audience = our resource ID), `docs/alexa/account-linking.md` with exact values to enter in the add-on config, test users.
- **Done when:** a manual OAuth authorization-code + PKCE run against the IdP yields a token that T1.2/T1.3 accept.

### [x] T1.8 — Privacy tooling: export, deletion, audit log
- **Depends on:** T1.1, T0.9 · **Est. LOC:** ~500
- **What it does:** Supports the privacy requirements for certification: users can get or erase their data.
- **Implement:** `audit_log` table (no sensitive payloads), module hook `export_user_data(user_id)` / `delete_user_data(user_id)` added to the `Module` protocol, `scripts/export_user.py`, `scripts/delete_user.py` (orchestrates all enabled modules in one transaction per module), retention job skeleton, privacy-policy draft in `docs/legal/`.
- **Done when:** after deletion no rows referencing the user remain (test enumerates all schemas); export returns a complete JSON bundle.

### [x] T1.9 — Security regression test suite
- **Depends on:** T1.3, T1.4, T1.5 · **Est. LOC:** ~400
- **What it does:** Locks in security behavior so later modules cannot silently break it.
- **Implement:** reusable pytest helpers: `assert_user_isolation(tool, ...)` (user A cannot read/modify user B's records via any ID), token fuzzing, rate-limit tests, log-redaction tests, a CI job that runs every registered tool through the isolation helper automatically.
- **Done when:** the suite auto-discovers tools; adding a tool without isolation coverage fails CI.

---

# PHASE 2 — Shared services

### [x] T2.1 — LLM port, fake client, and router
- **Depends on:** T0.7, T0.12 · **Est. LOC:** ~700
- **What it does:** One interface for all language-model calls with reliability features, so providers are swappable and failures are contained.
- **Implement:** `shared/llm/ports.py` (`generate_json(prompt, schema, ...)`, `generate_text(...)`), `fake.py` (deterministic fixtures, scripted failures), `router.py` (primary/fallback, retries with jitter, per-provider concurrency limit, circuit breaker, daily request/token budget in Redis, timeouts), metrics (calls, tokens, latency, failures).
- **Done when:** tests cover fallback on error, circuit opening/closing, budget exhaustion → `upstream_unavailable`, and timeout enforcement.

### [x] T2.2 — Gemini adapter
- **Depends on:** T2.1 · **Est. LOC:** ~300
- **What it does:** Real calls to Google's Gemini (default provider) with structured JSON output.
- **Implement:** `shared/llm/gemini.py` using the official SDK, JSON/schema mode, safety-setting config, usage accounting, error classification (rate limit vs auth vs bad request), model ID read from config only. **Check current model names and free-tier limits in Google's docs at implementation time.**
- **Done when:** respx/mocked tests pass; one opt-in live test (`pytest -m live`) generates valid JSON for a sample schema.

### [x] T2.3 — Groq adapter
- **Depends on:** T2.1 · **Est. LOC:** ~300
- **What it does:** Fast fallback provider.
- **Implement:** `shared/llm/groq.py` mirroring the Gemini adapter, JSON-mode handling with Pydantic re-validation, rate-limit header parsing.
- **Done when:** mocked tests pass; router test shows Gemini failure → Groq success path.

### [x] T2.4 — Grounding client (Wikipedia) and content sanitizer
- **Depends on:** T1.4, T0.7 · **Est. LOC:** ~500
- **What it does:** Fetches trustworthy source text so quiz questions come from real material, not model memory.
- **Implement:** `shared/content/wikipedia.py` (search + summary/extract via the Wikimedia REST API, language param, disambiguation handling, redirects), response caching in Redis (TTL days), `sanitizer.py` (strip markup, cap length, remove instruction-like text patterns, wrap in delimiters), User-Agent per Wikimedia policy, allow-listed host only.
- **Done when:** tests with recorded fixtures cover found, ambiguous, missing, and injection-laden pages; outputs never exceed the length cap.

### [x] T2.5 — Background worker infrastructure
- **Depends on:** T0.3, T1.6, T0.12 · **Est. LOC:** ~400
- **What it does:** Runs long or scheduled work outside request handling.
- **Implement:** `worker.py` (arq worker, startup loading each module's `register_jobs`), cron-style scheduler support, job metrics, structured logging with job IDs, retry policy, graceful shutdown, event dispatcher job from T1.6 mounted here.
- **Done when:** a sample job enqueued from a tool runs in the worker container; failed jobs retry and surface in metrics.

---

# PHASE 3 — Academics module

### [x] T3.1 — Academics schema, models, migrations
- **Depends on:** T0.6, T0.9 · **Est. LOC:** ~600
- **What it does:** Creates all academics tables in their own Postgres schema.
- **Implement:** `modules/academics/models.py` and migration branch `academics` for `topics, questions, quizzes, quiz_questions, decks, cards, study_plans, plan_tasks, topic_stats` with constraints and indexes from PRD §11.2; enums as DB types; `module.py` skeleton registering nothing yet.
- **Done when:** migration up/down tests pass; constraint tests (exactly-one-correct is enforced in code, `content_hash` uniqueness, FK integrity) pass.

### [x] T3.2 — Topic normalization and question-bank repository
- **Depends on:** T3.1 · **Est. LOC:** ~500
- **What it does:** Maps messy spoken topics to canonical keys and stores/fetches questions efficiently.
- **Implement:** `domain/topics.py` (normalize, slug, alias table, length limits), `ports.py` (`QuestionBankPort`), SQLAlchemy repo (`find_questions(topic_key, difficulty, exclude_ids, limit)`, `insert_questions` with dedupe by `content_hash`, `count_available`, flag/quarantine operations).
- **Done when:** "Photosynthesis", "photosynthesis!", "  PHOTOSYNTHESIS " map to one key; dedupe and exclusion queries tested; query-count assertions show no N+1.

### [x] T3.3 — Question generation pipeline: prompts, parsing, validation
- **Depends on:** T2.1, T2.4, T3.2 · **Est. LOC:** ~900
- **What it does:** Turns a topic into validated multiple-choice questions grounded in source text.
- **Implement:** `prompts/quiz_gen_v1.md` (with version constant), `adapters/generation.py` — normalize → fetch grounding (fallback: LLM-only with `grounded=false` flag) → generate N+buffer questions as strict JSON → Pydantic validation (4 distinct options, exactly 1 correct, stem/option length limits, no answer leakage in stem, option-order shuffling with stored `correct_key`) → dedupe → return validated set with reject stats; prompt-injection delimiting.
- **Done when:** FakeClient fixtures for valid, malformed JSON, duplicate options, two-correct, leaking-stem, and injection text all produce the expected accept/reject results.

### [x] T3.4 — Verification pass and quarantine loop
- **Depends on:** T3.3 · **Est. LOC:** ~450
- **What it does:** Catches wrong answers before users see them.
- **Implement:** second-pass verification (answer the question from the source using a different prompt, preferably the other provider), discard on disagreement, `status` transitions (`approved/flagged/quarantined`), `flag_question` service method, quarantine threshold in config, metrics for reject rate.
- **Done when:** a seeded wrong-answer question is rejected by verification in tests; flagged questions drop out of serving queries.

### [x] T3.5 — Quiz domain logic: answer matching and scoring
- **Depends on:** T3.1 · **Est. LOC:** ~500
- **What it does:** Pure, deterministic rules for understanding a spoken answer and scoring it.
- **Implement:** `domain/answer_matching.py` (letters, "option B", ordinals "second", numerals, exact text, fuzzy text via rapidfuzz with threshold, ambiguity detection returning a clarification result), `domain/scoring.py`, quiz state machine (`active → finished | expired`), Hypothesis property tests (never matches two options at once; idempotent on re-normalization).
- **Done when:** a table of ≥ 60 spoken-answer cases passes, including speech-recognition-style errors ("be" for "B", "for" for "four").

### [x] T3.6 — Quiz service and `quiz_start` tool
- **Depends on:** T3.2, T3.3, T3.5, T1.3, T1.5 · **Est. LOC:** ~800
- **What it does:** The first user-facing capability: "quiz me on X".
- **Implement:** `service/quiz.py::start_quiz` (topic or `weak_topics`/`due_review` sources, cache lookup → synchronous first-batch generation within the time budget → create quiz with ordered `quiz_questions`), `tools/quiz.py::quiz_start` with PRD §10.1 description/schema (anonymous allowed, `request_id` idempotency), envelope with spoken summary, never includes the correct key, rate limit on generation path.
- **Done when:** contract test: `quiz_start` returns `quiz_id`, question 1 of N, options A–D, no answer; cache-hit path p95 ≤ 1 s locally; miss path uses the FakeClient pipeline; snapshot updated.

### [x] T3.7 — `quiz_answer` tool, completion, summary, events
- **Depends on:** T3.6 · **Est. LOC:** ~600
- **What it does:** Evaluates answers, advances the quiz, and finishes with a summary.
- **Implement:** `service/quiz.py::answer_question` (ownership/anonymous-handle check, TTL expiry → `not_found`, ambiguity → `invalid_input` without consuming the attempt, record attempt, explanation, next question or final summary), `tools/quiz.py::quiz_answer`, publish `quiz.finished` event with per-topic correct/total, idempotent on `request_id`.
- **Done when:** full 5-question flow passes in a contract test (correct, incorrect, ambiguous, expired, replayed `request_id`); user-isolation helper passes.

### [x] T3.8 — Prefetch, bank expansion, and expiry jobs
- **Depends on:** T3.6, T2.5 · **Est. LOC:** ~450
- **What it does:** Keeps quizzes fast by generating ahead of the user, and cleans up stale state.
- **Implement:** `jobs.py` — `expand_bank(topic_key, difficulty)` (triggered after a miss and when available-count falls below a threshold, with a Redis lock to prevent duplicate generation), `prefetch_adjacent_difficulty`, `expire_quizzes` cron, `popular_topics_pregen` cron (config-driven topic list).
- **Done when:** after one miss, the worker fills the bank so the next `quiz_start` is a cache hit; duplicate triggers produce one generation.

### [x] T3.9 — Spaced repetition (shared SM-2) and flashcard persistence
- **Depends on:** T3.1, T0.9 · **Est. LOC:** ~600
- **What it does:** Schedules reviews so cards come back just before forgetting. Placed in shared code so the language module can reuse it.
- **Implement:** `shared/srs/sm2.py` (pure functions: next interval, ease, repetitions from rating `again/hard/good/easy`), property tests (ease floor, monotonic intervals for good answers), academics repos for `decks/cards` (create, next-due, grade, list-due counts), service layer. *(Update PRD §7 to list `shared/srs/`.)*
- **Done when:** SM-2 behaves per reference table in tests; due-card query uses the `(user_id, due_at)` index (verified by test/EXPLAIN assertion).

### [x] T3.10 — `flashcards` tool
- **Depends on:** T3.9, T1.3 · **Est. LOC:** ~450
- **What it does:** Voice flashcards: add, review, grade, list due.
- **Implement:** `tools/flashcards.py` with `action` enum (`add, review_next, grade, list_due`), per-action validation, `auth_required` for anonymous users, spoken flow ("Front: … Say 'show answer' or grade it"), idempotent `add`.
- **Done when:** contract test runs add → review_next → grade → list_due with correct rescheduling; isolation tests pass.

### [x] T3.11 — Study plan scheduling domain
- **Depends on:** T3.1 · **Est. LOC:** ~500
- **What it does:** Deterministic day-by-day planning (code, not LLM guesswork).
- **Implement:** `domain/planner.py` — inputs: exam date, topics with optional weights, hours/day, user timezone; outputs: dated tasks that distribute topics (more time for weak topics), include review days and a buffer before the exam, handle too-little-time cases explicitly (returns a feasibility warning), pure functions with a `Clock` port.
- **Done when:** property tests: total minutes never exceed capacity, last days are review, plan covers every topic or reports it could not.

### [x] T3.12 — `study_plan` tool (with LLM topic breakdown)
- **Depends on:** T3.11, T2.1, T1.3 · **Est. LOC:** ~550
- **What it does:** "Make a study plan for chemistry exam on the 15th" and "what should I study today".
- **Implement:** `service/plan.py` (if the user gives only a subject, optionally ask the LLM for a topic breakdown as validated JSON; scheduling stays in domain code), `tools/study_plan.py` with `action` enum (`create, today, update, list`), date parsing assistance (accepts ISO and relative inputs validated server-side with timezone), mark tasks done, replan remaining days on `update`.
- **Done when:** contract test creates a plan, fetches today's tasks, marks one done, and replans; invalid/past dates give helpful `invalid_input`.

### [x] T3.13 — Progress statistics and `progress_report` tool
- **Depends on:** T3.7, T1.6 · **Est. LOC:** ~550
- **What it does:** Weak topics, streaks, weekly summary.
- **Implement:** event handler for `quiz.finished` / `flashcard.graded` updating `topic_stats`, streak calculation in user timezone (domain function), `service/progress.py`, `tools/progress.py::progress_report` with `scope` enum (`summary, weak_topics, streak, weekly`), `quiz_start(source="weak_topics")` integration.
- **Done when:** after scripted quizzes, weak-topic ranking and streak are correct across timezone/day boundaries; handler is idempotent under duplicate events.

### [x] T3.14 — `topic_brief` tool
- **Depends on:** T2.4, T2.1 · **Est. LOC:** ~350
- **What it does:** A short, sourced spoken overview of a topic.
- **Implement:** `service/brief.py` (retrieve grounding → LLM summarizes strictly from the text → length-capped; falls back to the extract itself), `tools/brief.py` returning `data.sources`, cache by topic+length, anonymous allowed.
- **Done when:** output contains only source-derived content in tests with the FakeClient; length caps respected; sources always present.

### [x] T3.15 — Academics integration: tool budget resolution, descriptions, end-to-end suite
- **Depends on:** T3.6–T3.14 · **Est. LOC:** ~600
- **What it does:** Makes the whole module coherent and ready for Alexa+.
- **Implement:** resolve the tool-count ADR using T0.13's V1 finding (merge to `quiz(action)` / `learning_insights(kind)` if required), rewrite every tool description with use/avoid/example phrases, e2e contract scenarios replaying the PRD §2.1 dialogs, snapshot regeneration, academics `api.py` for cross-module use (`get_streak`, `get_weak_topics`), `export_user_data/delete_user_data` implementations.
- **Done when:** all PRD §2.1 dialogs pass as scripted contract tests; tool budget test green; privacy export/delete covers every academics table.

---

# PHASE 4 — Infrastructure, Alexa+ integration, hardening, certification

### [x] T4.1 — Terraform: network, database, cache
- **Depends on:** T0.3 · **Est. LOC:** ~800
- **What it does:** Reproducible cloud foundations.
- **Implement:** `infra/terraform/` modules: VPC (private subnets, NAT), RDS PostgreSQL (multi-AZ in prod, encrypted, PITR, parameter group, separate migrator/app roles), ElastiCache Redis (encrypted in transit/at rest), security groups, remote state with locking, `staging` and `prod` workspaces/vars.
- **Done when:** `terraform plan` clean; staging applies; app role cannot run DDL (verified by a test script).

### [x] T4.2 — Terraform: application platform, secrets, DNS, TLS
- **Depends on:** T4.1, T1.7 · **Est. LOC:** ~800
- **What it does:** Runs the containers publicly over HTTPS.
- **Implement:** ECR repo, ECS Fargate services (app ≥ 2 tasks, worker 1), ALB with ACM certificate and HTTP→HTTPS redirect, Route 53 record for the public domain, Secrets Manager entries injected as env, autoscaling policies (CPU + request latency), log groups, IAM least privilege. Provide `docs/deploy/low-cost.md` for a Cloud Run/Fly/Render alternative.
- **Done when:** staging serves `https://<domain>/healthz` and `/mcp` with a valid certificate; MCP Inspector connects over the public URL.

### [x] T4.3 — Continuous delivery pipeline
- **Depends on:** T4.2, T0.4 · **Est. LOC:** ~400 (YAML + scripts)
- **What it does:** Safe, repeatable releases.
- **Implement:** `release.yml`: build and push image tagged by SHA → run migrations (expand-only) → deploy to staging → run contract suite against staging URL → manual approval → prod rolling deploy → post-deploy smoke test → automatic rollback on failed health; a separate manual workflow for `alexa-ai deploy` gated by "tool snapshot changed".
- **Done when:** a deliberately broken build is rolled back automatically; a good build reaches prod with zero failed requests in the smoke window.

### [x] T4.4 — Dashboards and alerts as code
- **Depends on:** T0.12, T4.2 · **Est. LOC:** ~500
- **What it does:** Turns metrics into operations you can act on.
- **Implement:** CloudWatch/Grafana dashboards and alarms: error rate > 1% (5 min), p95 over budget, LLM fallback spike, queue backlog, DB connections > 80%, certificate expiry, budget exhaustion; SLO definition (99.9% availability), alert routing config.
- **Done when:** a forced failure in staging triggers the expected alert; dashboards show per-tool latency and error rates.

### [x] T4.5 — Alexa+ add-on creation and listing **[VERIFY]**
- **Depends on:** T3.15, T4.2, T1.7, T0.13 · **Est. LOC:** ~200 (config/docs)
- **What it does:** Registers our MCP server with Alexa+ so it becomes an add-on.
- **Implement:** install/sign in to the Alexa AI CLI (`alexa-ai configure`); create the add-on via the Add-on Agent Skill or `alexa-ai new mcp --name ... --locale ... --mcp-server-url https://<domain>/mcp`; review and edit generated `shortDescription`, `fullDescription`, and `examplePhrases` (PRD §19.1); fill account-linking details from `docs/alexa/account-linking.md`; commit the generated `alexa/` project; `alexa-ai deploy`; record the Add-on ID/version in docs.
- **Done when:** the add-on deploys successfully and Alexa+ discovers all tools (visible in the Local Inspector).

### [x] T4.6 — Alexa+ test plans and scripts
- **Depends on:** T4.5 · **Est. LOC:** ~300 (docs/scripts)
- **What it does:** Repeatable testing in Amazon's tools, not just ours.
- **Implement:** `docs/alexa/test-plans.md` with scripted utterance lists for: quiz happy path, wrong/ambiguous answers, expired quiz, unlinked vs linked, flashcards, planner, progress, brief, error/timeouts; Local Inspector checklist (widget rendering, readiness report); Web Simulator multi-turn scripts; physical-device checklist; a "post-redeploy smoke" subset.
- **Done when:** every PRD §2.1 dialog passes in the Web Simulator and results are recorded.

### [x] T4.7 — Load testing and performance tuning
- **Depends on:** T4.2, T3.15 · **Est. LOC:** ~400
- **What it does:** Proves the latency and scale targets.
- **Implement:** k6/Locust scenarios (`quiz_start` cache-hit, `quiz_answer`, mixed traffic, burst), DB pool and worker-count tuning, slow-query review (add indexes), cache tuning, results in `docs/perf/report.md`.
- **Done when:** PRD §1.5 targets met at 100 RPS on the planned instance size; no N+1; bottlenecks documented.

### [x] T4.8 — Threat model, runbooks, backup and restore drill
- **Depends on:** T4.2, T1.9 · **Est. LOC:** docs + ~200 scripts
- **What it does:** Makes the product operable and defensible.
- **Implement:** STRIDE threat model in `docs/security/threat-model.md`, runbooks (deploy, rollback, provider outage, key rotation, DB restore, add-on redeploy, user-data request), a tested restore drill from backup into a scratch environment, secret-rotation procedure verified once.
- **Done when:** restore drill succeeds with documented timings; every threat has a mitigation or an accepted-risk note.

### [x] T4.9 — Certification and launch **[VERIFY]**
- **Depends on:** T4.6, T4.8, T0.13 · **Est. LOC:** docs
- **What it does:** Gets the add-on approved for real users.
- **Implement:** complete the certification checklist from the official guidelines, publish the privacy policy and support contact, run the physical-device test, submit, handle feedback, record the approved version.
- **Done when:** certification passes; the live add-on works for a real linked account end to end.

### [x] T4.10 — Developer documentation
- **Depends on:** T3.15 · **Est. LOC:** docs
- **What it does:** Lets anyone contribute or add a module safely.
- **Implement:** `README.md` (quick start), `docs/dev-guide.md`, `docs/module-authoring.md` (step-by-step from `_template`, tool-writing rules, checklist), `docs/architecture.md` with diagrams, ADR index, `CONTRIBUTING.md`.
- **Done when:** a new contributor follows the guide from a clean machine to a running server and a passing test run without help.

---

# PHASE 5 — Productivity module

> Each module phase follows the same pattern: schema → services → thin tools → contract tests → privacy hooks. **No changes to `core/` are allowed**; if one seems necessary, write an ADR first.

### [x] T5.1 — Productivity schema and `tasks` tool
- **Depends on:** T3.15 (pattern), T1.3 · **Est. LOC:** ~900
- **What it does:** "Add a task: submit report by Friday", "what's on my list?", "mark it done".
- **Implement:** module `productivity` from `_template`, schema `productivity` (`tasks` with title, due_at, priority, status, tags, list), service (create, list with filters, complete, reschedule, delete), `tools/tasks.py` with `action` enum, natural-date handling validated server-side, idempotent create, export/delete hooks, migrations, contract tests.
- **Done when:** full task lifecycle passes via MCP client; isolation tests pass; snapshot updated.

### [x] T5.2 — `habits` tool and streak events
- **Depends on:** T5.1, T1.6 · **Est. LOC:** ~700
- **What it does:** Habit tracking with streaks.
- **Implement:** tables `habits`, `habit_logs`; streak domain function (timezone-aware, grace rules in config); `tools/habits.py` (`create, log, status, list`); publish `habit.completed`; academics subscribes to count study habits toward streak summaries (via event only).
- **Done when:** streaks correct across timezone boundaries and missed days; event consumed idempotently.

### [x] T5.3 — `notes` tool (voice journal)
- **Depends on:** T5.1 · **Est. LOC:** ~550
- **What it does:** Save and search quick notes by voice.
- **Implement:** `notes` table with Postgres full-text search index, `tools/notes.py` (`add, search, read_latest, delete`), length caps, spoken-friendly truncation with "ask me to read more", privacy export/delete.
- **Done when:** search finds notes by partial words; long notes are chunked for speech.

### [x] T5.4 — `focus_timer` tool
- **Depends on:** T5.1, T2.5 · **Est. LOC:** ~450
- **What it does:** Pomodoro-style focus sessions with history.
- **Implement:** `focus_sessions` table, `tools/focus.py` (`start, status, stop, history`), server computes remaining time from stored timestamps (no live timers needed), optional completion-time recording. **[VERIFY]** whether Alexa+ offers a way for add-ons to notify when time is up; if not, rely on the user asking "how much time is left?" and document the limitation.
- **Done when:** start/status/stop produce correct remaining times under a fake clock; history aggregates correctly.

### [x] T5.5 — `daily_briefing` tool (cross-module via published APIs)
- **Depends on:** T5.1, T5.2, T3.13 · **Est. LOC:** ~450
- **What it does:** "Give me my day": tasks due, habits pending, today's study plan, due flashcards.
- **Implement:** `daily_briefing` in productivity calling **only** `academics.api` and productivity services (module enabled/disabled aware: skips sections for disabled modules via a registry capability check), ordered, concise spoken summary.
- **Done when:** briefing adapts when academics is disabled; no import-linter violations.

---

# PHASE 6 — Finance module

### [x] T6.1 — Finance schema and `expense_log` tool
- **Depends on:** T5.1 (pattern) · **Est. LOC:** ~800
- **What it does:** "Add 200 rupees for groceries."
- **Implement:** schema `finance` (`accounts?` optional, `expenses` with **integer minor units** and ISO currency, category, note, occurred_at), category normalization (rule-based + optional LLM suggestion), `tools/expense_log.py` (`add, list, undo_last, delete`), amount parsing safeguards ("two hundred" handled by Alexa+, we validate numeric range and currency), default currency per user.
- **Done when:** no floating-point money anywhere (lint/test); undo and idempotency work; isolation tests pass.

### [x] T6.2 — `budget` tool
- **Depends on:** T6.1 · **Est. LOC:** ~600
- **What it does:** Monthly category budgets and "how much is left?".
- **Implement:** `budgets` table, domain calculations (period boundaries in user timezone, remaining, projected overspend), `tools/budget.py` (`set, status, list, remove`), threshold events (`budget.threshold_crossed`) stored for the next interaction.
- **Done when:** calculations correct at month boundaries and on leap days; status shows spoken-friendly amounts.

### [x] T6.3 — `split_bill` tool
- **Depends on:** T6.1 · **Est. LOC:** ~650
- **What it does:** "Split 1,200 among four of us" and track who owes whom.
- **Implement:** `groups`, `group_members` (named participants, not requiring accounts), `shared_expenses`, `settlements`; domain split algorithms (equal, by share, exact), rounding that never loses a paisa (largest-remainder method, property-tested), `tools/split_bill.py` (`split, balances, settle`).
- **Done when:** property tests show shares always sum to the total; balances net to zero across a group.

### [x] T6.4 — `finance_report` tool and reminders
- **Depends on:** T6.1, T6.2, T2.5 · **Est. LOC:** ~600
- **What it does:** Weekly/monthly summaries; bill and EMI due-date tracking.
- **Implement:** reporting queries (by category/period, comparisons with previous period), `bills` table for recurring due dates, `tools/finance_report.py` (`summary, by_category, bills_due, add_bill`), a cron job computing upcoming dues. **[VERIFY]** proactive notification support; until verified, dues are surfaced in `daily_briefing` and on request.
- **Done when:** reports reconcile exactly with logged expenses in tests; recurring bills roll forward correctly.

---

# PHASE 7 — Health module

### [x] T7.1 — `health_log` tool

- **Depends on:** T5.1 (pattern) · **Est. LOC:** ~800
- **What it does:** Log water, meals, workouts, sleep, and weight by voice. **Logging only; no medical advice** (PRD §1.4).
- **Implement:** schema `health` (`entries` with kind enum and typed JSON payload validated per kind, units handling metric/imperial), `tools/health_log.py` (`log, list, undo_last`), plausibility checks (reject absurd values with a friendly message), disclaimer text in tool description and spoken responses where relevant, privacy marking of this data as sensitive (stricter log redaction, shorter default retention config).
- **Done when:** validation tests per kind pass; health data never appears in logs; export/delete hooks cover it.

### [x] T7.2 — Medicine reminders and `health_summary` tool

- **Depends on:** T7.1, T2.5 · **Est. LOC:** ~650
- **What it does:** Medicine schedule tracking and weekly health summaries.
- **Implement:** `medicines`, `medicine_doses` tables, schedule domain logic (times, days, taken/missed), `tools/health_summary.py` (`today, week, medicines_due, mark_taken`), averages and trends computed in code. **[VERIFY]** proactive reminders (same caveat as T6.4). Include a safety note: the product does not give dosing advice.
- **Done when:** due/missed logic correct across timezones; weekly summary matches raw entries.

---

# PHASE 8 — Career module

### [x] T8.1 — `interview_practice` tool
- **Depends on:** T2.1, T3.9 (pattern) · **Est. LOC:** ~800
- **What it does:** Mock interviews by voice with feedback.
- **Implement:** schema `career` (`interview_sessions`, `interview_turns`), question generation by role/level (validated JSON, cached), answer evaluation rubric via LLM (structured scores: clarity, relevance, depth + 2 improvement tips), session handle IDs, `tools/interview.py` (`start, answer, finish, history`), feedback length tuned for speech, prompt versioning.
- **Done when:** FakeClient tests cover rubric parsing and malformed output; a full 5-question session works through the MCP client.

### [x] T8.2 — `application_tracker` tool
- **Depends on:** T8.1 (schema/module) · **Est. LOC:** ~550
- **What it does:** Track job applications and statuses.
- **Implement:** `applications` table (company, role, status enum, dates, notes), `tools/applications.py` (`add, update_status, list, due_followups`), follow-up date logic, spoken pipeline summary.
- **Done when:** lifecycle and filters pass in contract tests; follow-ups appear in `daily_briefing` when enabled (via published API).

### [x] T8.3 — `career_practice` tool (resume bullets, daily question)
- **Depends on:** T8.1 · **Est. LOC:** ~600
- **What it does:** Improve a resume bullet by voice and serve a daily coding/aptitude question.
- **Implement:** `tools/career_practice.py` with `kind` enum (`improve_bullet, daily_question, check_answer`), bullet-improvement prompt returning 2 variants with reasoning kept short, daily-question bank generated and validated like quiz questions (reuse generation helpers through `shared/` or the academics published API—decide via ADR), streak hook.
- **Done when:** outputs are validated, concise, and deterministic under FakeClient; daily question rotates without repeats per user.

---

# PHASE 9 — Home and family module

### [x] T9.1 — Households and sharing model **[ADR first]**
- **Depends on:** T1.1 · **Est. LOC:** ~700
- **What it does:** Lets several people share lists and chores safely. This is the first module with multi-user data, so authorization must be designed carefully.
- **Implement:** ADR on sharing model (household with roles `owner/member`), schema `home` (`households`, `memberships`, `invites` with expiring codes), service enforcing membership checks on every query, generic `assert_member` helper, privacy implications for deletion (shared data ownership rules), extended isolation test helper for shared resources.
- **Done when:** a non-member can never read/modify household data (tests across all repo methods); invite flow works end to end.

### [x] T9.2 — `shared_list` tool
- **Depends on:** T9.1 · **Est. LOC:** ~600
- **What it does:** "Add milk to the shopping list" shared by the family.
- **Implement:** `lists`, `list_items` tables, `tools/shared_list.py` (`add, remove, read, check_off, clear_checked`), dedupe/merge by normalized item name, quantity parsing, last-write-wins conflict policy documented.
- **Done when:** two users modify the same list concurrently without corruption; item normalization tested.

### [x] T9.3 — `chores` and `pantry_recipes` tools
- **Depends on:** T9.1, T2.1 · **Est. LOC:** ~900
- **What it does:** Chore rotation; pantry inventory; recipe lookup and a simple meal planner.
- **Implement:** `chores` (rotation logic domain function, fairness test), `pantry_items` with quantities/expiry, `tools/chores.py` (`assign, whose_turn, complete, add`), `tools/pantry_recipes.py` (`pantry_add, pantry_list, suggest_recipes, meal_plan`) — recipe suggestions via validated LLM JSON constrained to pantry items, allergy/diet preferences stored per household, ingredient-to-shopping-list handoff through `home` internal services.
- **Done when:** rotation is fair over N weeks in a property test; recipe output validation rejects missing/unknown ingredients.

---

# PHASE 10 — Small business module

### [x] T10.1 — Business tenancy and `orders` tool
- **Depends on:** T9.1 (membership pattern) · **Est. LOC:** ~900
- **What it does:** A shopkeeper says "what orders are pending?" and "mark order 12 shipped".
- **Implement:** schema `business` (`businesses`, `business_members`, `orders`, `order_items`, `customers`), human-friendly sequential order numbers per business (race-safe), status machine (`pending → packed → shipped → delivered/cancelled`), `tools/orders.py` (`create, list_pending, update_status, get`), money as minor units, import path for CSV later (hook only).
- **Done when:** concurrent order creation yields unique sequential numbers; illegal status transitions rejected with spoken guidance.

### [x] T10.2 — `ledger` tool (customer dues)
- **Depends on:** T10.1 · **Est. LOC:** ~650
- **What it does:** Track who owes the business money.
- **Implement:** `ledger_entries` (append-only, credits/debits), balance computed from entries (never edited in place), `tools/ledger.py` (`add_due, record_payment, balance, top_dues`), reversal entries instead of deletes, daily reconciliation test.
- **Done when:** balances always equal the sum of entries; reversals leave an audit trail.

### [x] T10.3 — `sales_summary` tool and low-stock alerts
- **Depends on:** T10.1 · **Est. LOC:** ~650
- **What it does:** "How were sales today?" and stock warnings.
- **Implement:** `products` with stock levels and thresholds, stock decrement on shipped orders (transactional), `tools/sales_summary.py` (`today, week, top_products, low_stock`), reporting queries with indexes, surfacing low-stock in `daily_briefing`.
- **Done when:** stock never goes negative under concurrent orders (tested); summaries reconcile to orders.

---

# PHASE 11 — Language learning module

### [x] T11.1 — `vocab` tool (daily vocabulary with spaced repetition)
- **Depends on:** T3.9, T2.1 · **Est. LOC:** ~700
- **What it does:** A word a day, quizzes on learned words, scheduled reviews.
- **Implement:** schema `language` (`words` cache by language/level, `user_words` with SM-2 state using `shared/srs`), word-of-the-day generation validated (word, meaning, example sentence, pronunciation hint in text), `tools/vocab.py` (`word_of_day, review, grade, stats`), supported language list in config (verify locale/speech behavior per V4).
- **Done when:** reviews reschedule correctly using the shared SM-2; duplicate words are not repeated for a user.

### [x] T11.2 — `language_practice` tool (conversation and translate-and-explain)
- **Depends on:** T11.1 · **Est. LOC:** ~650
- **What it does:** Practice short conversations and get grammar-aware translations.
- **Implement:** `tools/language_practice.py` (`start_conversation, reply, translate_explain, end`), turn-limited sessions with handle IDs, structured correction output (corrected sentence + one-line explanation), prompt guardrails, response length tuned for speech.
- **Done when:** FakeClient tests validate structured corrections; sessions expire and never exceed turn limits.

---

# PHASE 12 — Local and civic info module

> These tools depend on **external data sources whose availability, licensing, and terms must be verified before building**. Each task begins with an ADR documenting the source, license, rate limits, and fallback.

### [x] T12.1 — Data-source adapter framework
- **Depends on:** T1.4, T0.7 · **Est. LOC:** ~600
- **What it does:** A safe, cached way to call outside data APIs.
- **Implement:** `modules/local_info/` skeleton, `DataSource` port, HTTP adapter base (allow-listed hosts, retries, timeouts, circuit breaker, response caching with source-specific TTL, stale-while-error policy), freshness metadata surfaced in answers ("as of …"), attribution helper.
- **Done when:** simulated upstream outages return cached data marked stale; no unbounded retries.

### [x] T12.2 — `transit_status` tool **[VERIFY data source]**
- **Depends on:** T12.1 · **Est. LOC:** ~600
- **What it does:** Train/bus status and departures.
- **Implement:** ADR choosing an official or licensed API (do not scrape sites that forbid it), adapter, station/route name resolution with fuzzy matching, `tools/transit.py` (`next_departures, status`), clear "unavailable" spoken fallback, caching.
- **Done when:** fixture-based tests pass; name resolution handles common misspellings and spoken forms.

### [x] T12.3 — `commodity_prices` tool **[VERIFY data source]**
- **Depends on:** T12.1 · **Est. LOC:** ~550
- **What it does:** Crop/market prices ("what is the wheat price in my nearest mandi?").
- **Implement:** ADR for the government open-data source and its terms, adapter, commodity/market alias tables, `tools/commodity.py` (`get_price, compare_markets, trend`), unit normalization (quintal/kg), date-freshness guard (warn when data is old).
- **Done when:** unit conversions tested; stale-data warnings appear in spoken output.

### [x] T12.4 — `scheme_finder` tool (government scheme eligibility)
- **Depends on:** T12.1 · **Est. LOC:** ~900
- **What it does:** Tells a user which schemes they may qualify for.
- **Implement:** curated, versioned dataset of schemes (YAML/JSON in repo with source links and "last verified" dates), declarative eligibility rules engine (age, income, state, occupation) as pure code, `tools/schemes.py` (`find, explain, check_eligibility`), conversation design that asks for **one missing fact at a time**, strong disclaimer ("check the official portal; this is guidance, not a decision").
- **Done when:** rules engine tested against a table of sample profiles; dataset validation script runs in CI and fails on missing source links.

---

# PHASE 13 — Multi-add-on scaling, cross-module features, v1.0

### [x] T13.1 — Deployment profiles and multiple add-ons (solves the tool-count limit)
- **Depends on:** T0.13, T4.3, ≥ 2 modules built · **Est. LOC:** ~600
- **What it does:** Alexa+ may handle only a limited number of tools well, so the product is split into several add-ons from **one codebase**.
- **Implement:** ADR defining add-on bundles (suggested: **Study** = academics; **Life** = productivity + finance + health; **Work** = career + business; **Home** = home + language + local info — adjust by V1 findings), deployment profiles via `ENABLED_MODULES` per service, per-profile tool snapshots, per-profile ECS service + ALB rule/path or subdomain, per-profile add-on config under `alexa/<bundle>/`, per-profile CI contract runs, routing of shared identity (one IdP, same `user_id` across bundles).
- **Done when:** each profile starts independently, exposes only its tools, passes its contract suite, and shows the same user's data consistently where modules overlap.

### [ ] T13.2 — Cross-module weekly report
- **Depends on:** T13.1, T3.13, T5.2, T6.4, T7.2 · **Est. LOC:** ~500
- **What it does:** One spoken weekly summary combining study, habits, spending, and health.
- **Implement:** `weekly_review` capability using published module APIs only; sections appear only for enabled modules and available data; concise spoken ordering; optional highlights ("longest study streak ever").
- **Done when:** output adapts to any enabled-module combination in tests.

### [ ] T13.3 — Feature flags, per-user module toggles, and admin CLI
- **Depends on:** T13.1 · **Est. LOC:** ~700
- **What it does:** Safely roll out tools and let users turn modules on or off.
- **Implement:** flag store (config + DB overrides, percent rollout by hashed `user_id`), user preference tool (`settings` with `enable_module/disable_module/status`) respecting the tool budget, admin CLI (`scripts/admin.py`: inspect user, flag question, quarantine topic, replay dead-letter events), audit logging of admin actions.
- **Done when:** a flagged-off tool returns a graceful message; dead-letter replay works; admin actions are audited.

### [ ] T13.4 — Full regression, release readiness, and v1.0
- **Depends on:** everything chosen for the release · **Est. LOC:** ~400 (tests/docs)
- **What it does:** Final proof that the whole system works and is supportable.
- **Implement:** run the complete contract + e2e + isolation + load suites against staging for every profile; Web Simulator regression for every add-on; dependency and container vulnerability review; SBOM and release notes; changelog; version tagging; final ADR/PRD reconciliation (PRD updated to match what was built); post-launch monitoring checklist (first 7 days).
- **Done when:** all suites green on staging; all add-ons certified; runbooks tested; v1.0.0 tagged and deployed; PRD and docs match reality.

---

## Appendix A — Dependency map (summary)

```
T0.1 → T0.2 → T0.5 → T0.9 → T0.10 → T0.11
T0.6 → T1.1 → T1.3 ← T1.2          T0.13 (research) feeds T1.3, T1.7, T3.15, T4.5, T4.9, T13.1
T1.6 (events) → T2.5 (worker) → T3.8 (jobs)
T2.1 (LLM) → T2.2/T2.3 → T3.3 → T3.4 → T3.6 → T3.7 → T3.13
T3.9 (SM-2) → T3.10 ; T3.11 → T3.12 ; T3.14 independent after T2.4
T3.15 → Phase 4 → Phase 5–12 (independent modules) → T13.x
```

## Appendix B — Size and effort guide
| Phase | Tasks | Approx. total LOC (incl. tests) |
|---|---|---|
| 0 | 13 | ~4,500 |
| 1 | 9 | ~3,500 |
| 2 | 5 | ~2,200 |
| 3 | 15 | ~9,000 |
| 4 | 10 | ~5,000 (incl. Terraform/YAML/docs) |
| 5–12 | 24 | ~16,000 |
| 13 | 4 | ~2,200 |

These are planning estimates, not limits; if a task is clearly heading past 2,000 lines, split it and update this file.

## Appendix C — Items that must not be assumed (re-check before the related task)
1. Alexa+ tool-count, timeout, and response-size limits (T0.13).
2. The exact account-linking flow and scopes for MCP add-ons (T1.3, T1.7).
3. Whether add-ons can send proactive notifications/reminders (T5.4, T6.4, T7.2).
4. Supported locales and languages (T11.1, launch locale).
5. Free-tier model names, limits, and data-use terms of LLM providers (T2.2, T2.3).
6. Licensing and terms of every external data source (Phase 12).
7. Certification requirements for each add-on (T4.9, T13.4).
