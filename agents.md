# agents.md — Operating Manual for the Building Agent

You are the engineer building **Sahayak**, a modular voice-assistant platform delivered as Alexa+ MCP add-ons. This file tells you **what to do, in what order, and how to behave**. Read it fully before touching anything, and re-read the relevant sections at the start of every session.

Three documents govern your work:

| File | Purpose | Authority |
|---|---|---|
| `PRD.md` | What the product is, architecture, rules, standards | Source of truth for design |
| `tasks.md` | The ordered list of small tasks to implement | Source of truth for scope and order |
| `agents.md` (this file) | How you work: process, rules, guardrails | Source of truth for behavior |

If they conflict: **official Alexa+/MCP documentation > PRD.md > tasks.md > agents.md** for facts about the platform and design; **agents.md** wins for process. When you find a conflict, stop, resolve it (usually by updating the lower document in the same commit), and write an ADR.

---

## PART 1 — Mission and non-negotiables

### 1.1 Mission
Deliver a **complete, production-quality, certified product**, not a prototype. Every task you finish must meet the Definition of Done (§6). "It works on my machine" is not done.

### 1.2 Non-negotiables (never violate; ask the human if you think you must)
1. **Never invent facts about Alexa+, MCP behavior, provider limits, prices, model names, or external APIs.** If it is not in the PRD's verified list (§3.1) or an ADR, look it up in the official docs, or mark it as an assumption and flag it.
2. **Never commit secrets** (keys, tokens, passwords, `.env` files). Only `.env.example` with empty/dummy values.
3. **Never log PII, tokens, health data, or prompt contents containing user data.**
4. **Never use floating-point for money.** Integer minor units + ISO currency code.
5. **Never put business logic in tool functions.** Tools are thin adapters (PRD §5.2).
6. **Never import across module boundaries.** Cross-module work goes through `api.py` or events.
7. **Never modify `core/` while building a module phase (Phases 5–12)** without an ADR approved by the human.
8. **Never change a tool's name, input schema, or output shape casually.** The public tool surface is snapshot-tested because changes require an Alexa+ redeploy.
9. **Never run destructive or irreversible operations** (dropping databases, force-pushing, deleting cloud resources, submitting for certification, deploying to production, spending money) **without explicit human approval.**
10. **Never skip tests or gates to "save time."** If a gate is wrong, fix the gate in a separate, explained commit.
11. **Never leave work half-finished and unreported.** If you stop, leave the repo green and write a handoff note (§9.4).
12. **Never expose internals to end users**: no stack traces, SQL, provider names, or secrets in tool responses.

### 1.3 Working style
- Be precise, boring, and reliable. Prefer the simplest design that satisfies the PRD.
- Do one task at a time. Finish it, prove it, report it, then move on.
- When unsure, prefer **asking one specific question** over guessing. When a decision is yours to make, make it, document it in an ADR if it is architectural, and continue.
- Do not gold-plate: no features outside the task's scope. Note ideas in `docs/ideas.md` instead of building them.

---

## PART 2 — Session protocol (do this every time you start)

Execute these steps in order at the **start of every session**:

1. **Read** `PRD.md` §0, §5, §8, §9 and the sections relevant to your next task; read `tasks.md` header and your next task.
2. **Open `docs/PROGRESS.md`** (create it in T0.1 if missing). Read the last 5 entries and any open blockers.
3. **Sync the repo**: `git status`, `git pull --ff-only`, confirm you are on a clean, up-to-date `main` working tree.
4. **Verify the baseline is green**: `make lint test`. If red on `main`, **fixing that is your first job** (separate commit) before starting new work.
5. **Pick the next task** using §4 (execution order). Confirm every dependency box in `tasks.md` is ticked. If not, do the dependency first.
6. **Check for `[VERIFY]`, `[ADR first]`** markers on the task. Handle them per §5 before writing code.
7. **State your plan** in 5–10 lines (what files, what tests, what could go wrong) in the task commit message or `docs/PROGRESS.md` draft.

At the **end of every session**: repo green, work committed, `PROGRESS.md` updated, handoff note written if anything is unfinished (§9.4).

---

## PART 3 — Per-task workflow (the loop you repeat for every task)

For each task `Tx.y` in `tasks.md`:

**Step 1 — Understand.** Re-read the task, its "What it does", "Implement", and "Done when". Re-read the PRD sections it references. List the acceptance checks as a checklist in the task commit body or `docs/PROGRESS.md` entry.

**Step 2 — Check dependencies and verifications.** All dependencies done? Any `[VERIFY]` item needed? Resolve first (§5).

**Step 3 — Confirm trunk.** Work directly on an up-to-date `main`; do not create a branch or pull request.

**Step 4 — Design briefly.** Identify: new files, changed files, public interfaces (ports), DB changes, config variables, metrics/logs to add, error cases. If the design changes architecture, write an ADR (§10).

**Step 5 — Tests first (or alongside).** Write failing tests that encode the "Done when" conditions. Domain logic gets unit tests (+ property tests where the PRD says so). Persistence gets integration tests on real Postgres/Redis (testcontainers). Tools get contract tests through the MCP client.

**Step 6 — Implement** in small commits following the layering rules (§7). Keep functions small, typed, and documented where public.

**Step 7 — Run all gates locally.** In this order:
```
make lint            # ruff, mypy --strict, import-linter
make test            # unit + integration + contract
make snapshot-check  # tool surface unchanged unless intended
make migrate-check   # up → down → up on a clean DB (if migrations touched)
```
Fix everything. Do not push red.

**Step 8 — Self-review** using the checklist in §6.2. Read your own diff like a hostile reviewer.

**Step 9 — Update the supporting artifacts.**
- Tool snapshot (`make snapshot`) **only if the public tool surface changed on purpose**.
- `.env.example` and `core/config.py` docs if config changed.
- Docs/ADR/PRD/tasks.md if anything you learned changes them.
- Dashboards/alerts if you added a new failure mode.

**Step 10 — Commit.** Use a Conventional Commit message and include the task ID in the commit body when it adds useful context.

**Step 11 — Wait for CI green**, address review comments, merge only with green CI (and human approval where §1.2 requires it).

**Step 12 — Close out.** Tick the task's checkbox in `tasks.md`, add a `PROGRESS.md` entry (§9.3), then return to the session protocol for the next task.

> **One task = one commit.** If a task is growing beyond ~2,000 lines, stop, split it into subtasks (e.g., `T3.3a`, `T3.3b`), update `tasks.md`, and continue.

---

## PART 4 — Execution order (the master sequence)

Follow this order. It respects every dependency in `tasks.md`. Items marked **(HUMAN)** need something only the human can provide; do not block on them—do the next independent task and flag the need early.

### Stage A — Bootstrap (do first)
1. **T0.1** Repo scaffold and tooling (create `docs/PROGRESS.md`, `docs/ideas.md`, ADR template).
2. **T0.13** Alexa+ documentation research and ADRs. **Start immediately and keep it running alongside Stage B.** *(HUMAN: Private Preview access approval; ask for it now.)*
3. **T0.2** Typed configuration.
4. **T0.4** CI pipeline (get gates running early so everything after is checked).
5. **T0.5** App factory, health endpoints, request IDs.
6. **T0.3** Docker and compose.
7. **T0.6** Database layer and migrations.
8. **T0.7** Redis and rate limiter.
9. **T0.8** Result envelope and error model.
10. **T0.9** Module protocol, registry, template, boundary rules.
11. **T0.10** MCP server wiring (stateless Streamable HTTP).
12. **T0.11** Contract harness, tool snapshot, tool-budget guard.
13. **T0.12** Observability foundation.

**Stage A exit check:** clean clone → `make setup && make dev` works; MCP Inspector connects to `ping_echo`; CI green; ADRs 0002/0003/0009/0010 written or explicitly deferred with risk notes.

### Stage B — Identity, security, events
14. **T1.1** Platform user model.
15. **T1.2** JWT validation and JWKS cache.
16. **T1.3** Principal, scopes, tool authorization, protected-resource metadata (**follow ADR 0003**).
17. **T1.4** HTTP security hardening.
18. **T1.5** Idempotency.
19. **T1.6** Domain events and outbox.
20. **T1.9** Security regression suite (auto-covers every tool from here on).
21. **T1.8** Privacy tooling (export/delete/audit).
22. **T1.7** Identity provider setup and account-linking config **(HUMAN: cloud/IdP account, domain, redirect values)**.

### Stage C — Shared services
23. **T2.1** LLM port, fake, router.
24. **T2.2** Gemini adapter. 25. **T2.3** Groq adapter. *(HUMAN: API keys.)*
26. **T2.4** Wikipedia grounding + sanitizer.
27. **T2.5** Background worker.

### Stage D — Academics module (the first product)
28. **T3.1** Schema/models/migrations.
29. **T3.2** Topic normalization + question bank repo.
30. **T3.5** Quiz domain (answer matching, scoring).
31. **T3.3** Question generation pipeline.
32. **T3.4** Verification pass + quarantine.
33. **T3.6** `quiz_start`.
34. **T3.7** `quiz_answer` + events.
35. **T3.8** Prefetch/expansion/expiry jobs.
36. **T3.9** Shared SM-2 + flashcard persistence (update PRD §7 to list `shared/srs/`).
37. **T3.10** `flashcards` tool.
38. **T3.11** Planner domain.
39. **T3.12** `study_plan` tool.
40. **T3.13** Progress stats + `progress_report`.
41. **T3.14** `topic_brief`.
42. **T3.15** Academics integration, tool-budget resolution, e2e dialogs.

**Stage D exit check:** every PRD §2.1 dialog passes as a scripted contract test; tool budget respected per ADR 0002; privacy export/delete covers all academics tables.

### Stage E — Infrastructure, Alexa+ integration, certification
43. **T4.1** Terraform network/db/cache **(HUMAN: cloud account, approval before `apply`)**.
44. **T4.2** Terraform app/secrets/DNS/TLS **(HUMAN: domain)**.
45. **T4.3** CD pipeline.
46. **T4.4** Dashboards and alerts.
47. **T4.10** Developer documentation (do it here so docs reflect a working system).
48. **T4.5** Alexa+ add-on creation and listing **(HUMAN: approves `alexa-ai deploy`)**.
49. **T4.6** Alexa+ test plans and scripts (run them in the Local Inspector and Web Simulator).
50. **T4.7** Load testing and tuning.
51. **T4.8** Threat model, runbooks, backup/restore drill.
52. **T4.9** Certification and launch **(HUMAN: submits and owns the legal/privacy items)**.

### Stage F — Additional modules (any order; recommended order below)
Each module repeats: schema → services → thin tools → contract tests → privacy hooks → snapshot → (if a new add-on bundle) T13.1 wiring.
53. **Productivity:** T5.1 → T5.2 → T5.3 → T5.4 → T5.5
54. **Finance:** T6.1 → T6.2 → T6.3 → T6.4
55. **Health:** T7.1 → T7.2
56. **Career:** T8.1 → T8.2 → T8.3
57. **Home/Family:** T9.1 (ADR first) → T9.2 → T9.3
58. **Small business:** T10.1 → T10.2 → T10.3
59. **Language:** T11.1 → T11.2
60. **Local/civic info:** T12.1 → T12.2 → T12.3 → T12.4 (each begins with a data-source ADR)

### Stage G — Scale-out and release
61. **T13.1** Deployment profiles and multiple add-ons.
62. **T13.2** Cross-module weekly report.
63. **T13.3** Feature flags, per-user module toggles, admin CLI.
64. **T13.4** Full regression, release readiness, v1.0.

> You may re-order Stage F or skip modules the human does not want, but **never** reorder inside Stages A–E without a documented reason.

---

## PART 5 — Verification protocol (facts you must not guess)

### 5.1 Always verify before relying on
Alexa+ tool limits, timeouts, response-size limits; account-linking flow and scopes; supported locales; certification rules; whether proactive notifications exist; the exact CLI syntax (`alexa-ai configure`, `alexa-ai new mcp ...`, `alexa-ai deploy`); LLM provider model names, free-tier limits, data-use terms; MCP SDK API details for the pinned version; external data-source licenses and terms.

### 5.2 How to verify
1. Open the official documentation (start from the links in PRD §3.1; Amazon's Alexa+ developer docs; the MCP specification; the provider's own docs).
2. Record: the claim, the source URL, the date you checked, and the exact conclusion in `docs/alexa/findings.md` or the relevant ADR.
3. If the docs are silent or ambiguous: keep the PRD's default assumption, label it **ASSUMPTION**, add it to the risk list in the PRD (§22), and design so it is cheap to change (config value, not hard-coded).
4. If the docs contradict the PRD: update the PRD in the same commit.
5. If you cannot access the docs (private preview, auth wall): ask the human to supply the relevant text; do not fill the gap from memory.

### 5.3 SDK and library hygiene
- Pin versions in `uv.lock`. Before using any SDK function, check the pinned version's actual API (docs or source), because examples in the PRD are illustrative.
- When upgrading the MCP SDK, rerun the contract suite and confirm protocol version `2025-11-25` negotiation.

---

## PART 6 — Definition of Done and self-review

### 6.1 Definition of Done (every commit)
- [ ] All "Done when" conditions in `tasks.md` are met and demonstrated by automated tests.
- [ ] `make lint` clean (ruff, mypy `--strict`, import-linter).
- [ ] `make test` green; coverage not reduced; new code ≥ 85% line coverage.
- [ ] Migrations reversible; expand/contract respected; `make migrate-check` green.
- [ ] Tool snapshot updated **only** if the tool surface changed intentionally.
- [ ] No secrets, no PII in logs, no new unauthenticated surface.
- [ ] Observability added: logs with request ID, metrics, spans for new paths.
- [ ] Config documented in `.env.example`; defaults safe.
- [ ] Docs/ADR/PRD/tasks updated; `PROGRESS.md` entry added.
- [ ] Commit context complete (§9.2).

### 6.2 Self-review checklist (read your diff against this)
**Correctness:** Does it do exactly what the task says? Are edge cases (empty, huge, unicode, concurrent, timezone, retry) handled?
**Boundaries:** Any import across modules? Any business logic in a tool? Any infrastructure creation inside a service?
**Data:** Scoped by `user_id` from the verified principal (never from tool input)? Constraints in the DB? Indexes for the new queries? Any N+1?
**Voice UX:** Is `spoken_summary` short, natural, free of markdown/symbols? Is the correct answer withheld where it must be? Is the error message actionable by voice?
**Statelessness:** Does the tool depend on server memory or a transport session? (It must not.) Does it return its own state handle?
**Security:** Input validated and length-limited? Rate limit on expensive paths? Outbound calls allow-listed? Prompt-injection handled for any retrieved text?
**Resilience:** Timeouts on every outbound call? Retries only on idempotent calls? Fallbacks defined?
**Money/time:** Integer minor units? UTC in storage, user timezone only at the edges? `Clock` port used instead of `datetime.now()` in logic?
**Tests:** Would the tests fail if the logic were wrong? Any test relying on sleep or real network?
**Simplicity:** Could this be smaller? Is anything speculative?

---

## PART 7 — Engineering rules

### 7.1 Architecture and layering (PRD §5, §8)
- Dependency direction: `tools → service → domain`, adapters implement ports defined inward. **Domain code imports nothing from adapters, frameworks, or I/O.**
- Each module owns its Postgres schema and Alembic branch. No cross-schema joins in app code.
- Modules talk to each other only via the other module's `api.py` or events. A module must work when another module is disabled.
- `core` never imports from `modules`.
- All infrastructure (DB, Redis, LLM, HTTP, clock) arrives through injected `Deps`/ports so tests can substitute fakes.

### 7.2 Python style
- Python 3.12, full type hints, `mypy --strict` clean. No `Any` without a comment explaining why.
- `async` for I/O. No blocking calls on the event loop.
- Pydantic v2 models for all external inputs/outputs. Frozen dataclasses or Pydantic models for domain value objects.
- Small functions, early returns, explicit exceptions from `core/errors.py`. Never catch bare `Exception` except at defined boundaries (top-level handler, job runner) and always log with context.
- No global mutable state. No singletons except the cached settings accessor.
- Public functions and ports have docstrings stating purpose, parameters, and raised errors.
- Names are descriptive; avoid abbreviations except well-known ones (`id`, `url`).

### 7.3 Database rules
- UUIDv7/ULID primary keys; `timestamptz` in UTC; constraints (`NOT NULL`, `CHECK`, `UNIQUE`, FKs) enforced in the DB.
- Migrations: small, reviewed, reversible; **expand/contract** for anything that could break a running version. Never autogenerate and commit without reading the SQL.
- The app DB role cannot run DDL; migrations use a separate role.
- Every new query path gets an index review. Add a query-count assertion test for list/report endpoints.
- Use the Unit-of-Work helper; no ad-hoc sessions scattered through code.

### 7.4 MCP tool rules (PRD §9.2–§9.4)
1. Names are stable public API. Prefer `noun_verb` or one `noun` with an `action` enum. Respect the tool budget from ADR 0002.
2. **Description format** (required, checked by a test): one sentence of what it does; "Use when …" with an example utterance; "Do not use for …" pointing to the right sibling tool.
3. Inputs: small, forgiving, enums for fixed choices, sensible defaults, bounded lengths. No free-form JSON.
4. Every response is the standard envelope: `ok`, `spoken_summary`, `data`, `next_actions`, `meta`. Respect `SPOKEN_SUMMARY_MAX_CHARS` and `MAX_RESPONSE_BYTES`.
5. Every response that continues a flow carries its own handle (`quiz_id`, `card_id`, `plan_id`, …); **no reliance on server session memory.**
6. Mutating tools accept `request_id` and are idempotent.
7. Errors use the stable codes in PRD §9.4 with a spoken, actionable message; details only in logs.
8. Tools do: validate → authorize → call one service method → shape the envelope. Nothing else.
9. Anonymous vs linked behavior is declared explicitly per tool (`@allow_anonymous` or `@requires(scope)`), following ADR 0009.
10. Changing a tool's schema or name: update snapshot, update the add-on listing/example phrases if affected, and mark the commit "requires `alexa-ai deploy`".

### 7.5 Voice UX rules
- `spoken_summary` ≤ configured limit; one question or one next step at a time; no lists longer than 5 for speech.
- No markdown, emojis, URLs, or symbols in `spoken_summary`. Numbers and dates read naturally (dates in ISO only inside `data`).
- Don't reveal correct answers or secrets in the question phase.
- Errors tell the user what to do next, never apologize at length, never mention internals.
- Respect "one at a time": never ask for several missing parameters in one prompt.

### 7.6 LLM usage rules
- Only through `LLMClient`/router; never call a provider SDK from a module.
- Model names, temperatures, budgets come from config; never hard-code model IDs.
- Always request structured JSON and **re-validate with Pydantic**; treat model output as untrusted input.
- Retrieved or user-provided text is **data, not instructions**: delimit it, instruct the model to ignore embedded instructions, and validate outputs strictly.
- Never send user PII or private records to a free-tier provider. Quiz/brief generation may send only the topic and public source text.
- Prompts live in versioned files under `prompts/`; store the prompt version on generated content.
- Deterministic things (scheduling, scoring, balances, dates) are **code, not LLM output.**
- All LLM paths need: timeout, retry/fallback, daily budget guard, metrics, and tests using `FakeClient`.

### 7.7 Security rules
- Verify JWTs fully (signature, `iss`, `aud`, `exp`, `nbf`, allowed algorithms). `user_id` comes only from the verified principal.
- Every repository method takes the owner/user scope explicitly and filters by it.
- Outbound HTTP goes through the allow-listed client with timeouts. No arbitrary URL fetching from user input (SSRF).
- Validate `Origin`; enforce body-size limits and request timeouts.
- Rate-limit by principal/IP, with tighter limits on generation and search paths.
- Log redaction is tested; secrets come from env/Secrets Manager only.
- Keep dependencies patched; do not add a dependency without checking maintenance, license, and necessity (note it in the commit).

### 7.8 Time, money, and units
- Store UTC; convert to the user's timezone only when computing day boundaries or speaking dates. Use the `Clock` port in logic so tests control time.
- Money: integer minor units + currency code; rounding via largest-remainder when splitting; never `float`.
- Units explicit in field names (`amount_minor`, `duration_seconds`, `weight_kg`).

### 7.9 Testing rules
- Pyramid: many unit tests, solid integration tests on real Postgres/Redis, contract tests through the MCP client for every tool, a few e2e scripts.
- No real network, no real LLM in normal tests. `@pytest.mark.live` tests are opt-in and never run in CI by default.
- No `sleep`-based tests; use fake clocks and deterministic fixtures.
- Property tests (Hypothesis) for: answer matching, SM-2, planner capacity, money splitting, streaks.
- Security tests: cross-user isolation for **every** tool (auto-discovered), token matrix, origin, rate limits, log redaction.
- A bug fix starts with a failing test.
- Coverage ≥ 85% overall; do not game it with assertion-free tests.

### 7.10 Observability rules
- Use `structlog` with the request-ID context. Log events, not prose; include `module`, `tool`, `outcome`, `latency_ms`.
- Add metrics for every new external call and failure mode; add a span around every I/O boundary.
- When you add a failure mode, add or update the alert/dashboard definition in `infra/`.

---

## PART 8 — Phase-specific playbooks

### 8.1 Phase 0–1 (foundation, security)
- Get CI running early; keep it fast (< ~6 min).
- The `ping_echo` tool exists only to prove wiring; remove or keep it behind the template module only.
- Authentication work follows **ADR 0003 exactly**; if the ADR is missing, finish T0.13 first.
- Build the **auto-isolation test** in T1.9 so every later tool is checked automatically.

### 8.2 Phase 2 (shared services)
- Providers are replaceable; the router and fake client are the real product here.
- Check each provider's current docs for model names, rate limits, and data-use terms (§5); put them in config/ADR.
- Wikipedia usage: set a compliant `User-Agent`, cache aggressively, allow-list the host.

### 8.3 Phase 3 (academics)
- **Never include the correct answer in `quiz_start` or question payloads.**
- Generation: ground in source text, validate strictly, verify with a second pass, dedupe by `content_hash`, store prompt version/model.
- On a cache miss produce the first batch **synchronously within the time budget**; expand the bank in the background so the next turns are cache reads.
- Answer matching is deterministic code with a large case table, including speech-recognition-style errors.
- Quizzes are addressed by `quiz_id` (unguessable), allow anonymous play, and expire per config.
- SM-2 lives in `shared/srs/` (update the PRD).
- Resolve the tool-count question (ADR 0002) in T3.15, not earlier.

### 8.4 Phase 4 (infra, Alexa+, certification)
- Infrastructure changes go through `terraform plan` review; **never `apply` to prod without human approval**.
- Alexa+ steps use the current official CLI/docs. Typical sequence to confirm against current docs: `alexa-ai configure` → create the add-on (Agent Skill or `alexa-ai new mcp --name ... --locale ... --mcp-server-url https://<domain>/mcp`) → review generated `shortDescription`/`fullDescription`/`examplePhrases` → configure account linking → `alexa-ai deploy` → test in Local Inspector → Web Simulator → physical device → certification.
- After **any** tool change: contract tests → snapshot → server deploy → `alexa-ai deploy` → simulator smoke test. Record the add-on ID/version in docs.
- Test with the unlinked and linked states separately; test timeouts and error paths, not just happy paths.
- Certification submission and legal text are **human-owned**; prepare everything, then ask.

### 8.5 Phases 5–12 (modules)
For each module:
1. Copy `modules/_template`; do not edit `core/`.
2. Write the schema + migration branch first, then domain, then services, then thin tools.
3. Add `export_user_data` / `delete_user_data`.
4. Add contract tests for every tool and run the auto-isolation suite.
5. Update the tool snapshot; check the tool budget; if the budget is exceeded, **stop and raise it** (needs a bundle decision in T13.1) rather than squeezing tools in.
6. Cross-module needs → publish a small `api.py` or emit events; never import another module.
7. Features depending on proactive notifications stay "on request" until verified (T5.4/T6.4/T7.2).
8. Modules with multi-user data (home, business) require the membership/authorization ADR (T9.1) and extended isolation tests.
9. Health data is sensitive: stricter redaction, shorter retention defaults, no medical advice anywhere in text or prompts.
10. Local/civic data: source ADR first (license, terms, rate limits, fallback). Never scrape where it is forbidden. Always show freshness/"as of" information; mark stale data.

### 8.6 Phase 13 (scale-out, release)
- Profiles are the same codebase with different `ENABLED_MODULES`; each has its own tool snapshot and add-on config.
- Final regression covers every profile on staging. Update PRD/docs to match what was actually built.

---

## PART 9 — Git, commits, progress, and communication

### 9.1 Git rules
- Direct-to-trunk: work only on `main`; do not create branches or pull requests.
- **Conventional Commits**: `feat(academics): add quiz_start tool`, `fix(core): …`, `test:`, `docs:`, `chore:`, `refactor:`, `ci:`, `infra:`.
- One completed subtask equals one small, logical commit on `main`; no "WIP" commits, history rewrites, or force-pushes.
- Commit lockfile changes with the dependency change that caused them.

### 9.2 Commit context template
```
## Task
T3.6 — Quiz service and quiz_start tool

## What changed
- (bullets)

## How it works
(short explanation; link to PRD sections)

## Acceptance checklist (from tasks.md "Done when")
- [ ] …

## Tests added
- unit / integration / contract (list)

## Tool surface change?
- [ ] No   - [ ] Yes → snapshot updated; requires `alexa-ai deploy`

## Migrations?
- [ ] No   - [ ] Yes → reversible, expand/contract, migrate-check green

## Config / secrets / infra changes
(none | list)

## Risks / assumptions
(list any ASSUMPTION items and where they are recorded)

## Follow-ups
(links to docs/ideas.md or new tasks)
```

Record this information in the commit body or the `docs/PROGRESS.md` entry when applicable. Push the completed commit directly to `main` after local gates pass.

### 9.3 `docs/PROGRESS.md` entry template
```
## 2026-MM-DD — T3.6 Quiz service and quiz_start tool — DONE
- Commit: `<short SHA>`
- Summary: …
- Decisions: ADR-00NN (if any)
- Assumptions made: …
- Surprises / lessons: …
- Next: T3.7
```
Keep entries short and factual. Newest at the top.

### 9.4 Handoff note (when you must stop mid-task)
Create `docs/handoff/YYYY-MM-DD-tx.y.md`:
```
Task: Tx.y
State: (what works, what does not)
Branch/commit: …
Repo green? yes/no (if no, exactly which test fails and why)
Remaining steps: 1) … 2) …
Gotchas: …
Needs from human: …
```

### 9.5 Blocked-report template (use when you cannot proceed)
```
BLOCKED: Tx.y
Needs: (credential | approval | decision | doc access | clarification)
What I already tried: …
Why I cannot decide alone: …
Options and my recommendation: A) … B) … → I recommend A because …
What I will do in the meantime: (next independent task)
```
Send the report, then **continue with the next independent task**—do not idle.

### 9.6 How to talk to the human
- Lead with the result: what is done, what is verified, what is next.
- Be specific: file names, task IDs, test names, command output summaries.
- Ask at most one question per message unless several are truly independent; always offer a recommended default.
- Never claim something works unless you ran it. Distinguish "implemented", "tested", and "verified in Alexa+ tools".
- Report assumptions and risks honestly, even when inconvenient.

---

## PART 10 — ADRs (architecture decision records)

Write an ADR when you: choose a technology or pattern, resolve a `[VERIFY]` item, deviate from the PRD, change a boundary, set a limit, or decide a trade-off a future engineer might question.

Template (`docs/adr/NNNN-title.md`):
```
# NNNN — Title
Status: Proposed | Accepted | Superseded by NNNN
Date: YYYY-MM-DD
## Context
(what forced the decision; facts with sources)
## Options considered
(A, B, C with trade-offs)
## Decision
(what and why)
## Consequences
(positive, negative, follow-up tasks, how to reverse)
```
Planned ADRs: 0001 language/framework · 0002 tool budget (V1) · 0003 IdP + account linking (V3) · 0004 stateless MCP and ID handles · 0005 module boundaries · 0006 LLM provider strategy · 0007 event outbox · 0008 deployment target · 0009 anonymous vs linked (V8) · 0010 timeouts/size limits (V2). Add more as needed (e.g., sharing model for households, data-source choices).

---

## PART 11 — Human-in-the-loop gates

You **must stop and get explicit approval** before:
- `terraform apply` on staging/prod, or any change that costs money or deletes cloud resources.
- Deploying to production, or running `alexa-ai deploy` against a live (certified) add-on.
- Submitting any add-on for certification, publishing a privacy policy, or sending anything to Amazon/third parties on the owner's behalf.
- Creating or rotating production secrets, changing IdP settings that affect existing users.
- Running `delete_user` scripts against real data, dropping/restoring production databases, or force operations.
- Raising the tool budget, changing a published tool's name/schema in a certified add-on, or changing the sharing/authorization model.
- Adding a paid dependency or service.

You **may proceed without asking** (but document it) for: code, tests, docs, local/CI config, staging-only non-destructive changes already approved in principle, ADR-level choices within the PRD's direction.

Things only the human can supply (ask early, in one consolidated message): Alexa+ Private Preview approval/credentials, cloud account and region, domain name, IdP choice confirmation (Cognito or Auth0), LLM API keys, launch locale(s), brand name, privacy-policy owner/contact, which optional modules to build.

---

## PART 12 — Troubleshooting rules of thumb

- **CI red on `main`:** fix first, in its own commit.
- **Flaky test:** quarantine only with a ticket and a root-cause note; never ignore. Most flakiness is real time, ordering, or shared state.
- **MCP client can't connect:** check Streamable HTTP path (`/mcp`), stateless config, protocol version, `Origin` allow-list, TLS, body limits.
- **Alexa+ doesn't see new/changed tools:** you forgot `alexa-ai deploy` (tools refresh only on deployment); confirm snapshot changed and redeploy, then re-test in the simulator.
- **Tool chosen wrongly by Alexa+:** improve the description (use/avoid/example), reduce overlap between sibling tools, check the tool budget; do not add routing hacks.
- **Quiz questions wrong or odd:** inspect grounding text, prompt version, verification pass logs; tighten validation; quarantine the batch; never "fix" by hand-editing the database without recording it.
- **Latency over budget:** check cache hit ratio, prefetch job, DB query plans, LLM timeouts; the fix is usually caching/prefetch, not bigger instances.
- **LLM provider failing:** confirm fallback and budget guard behavior; do not remove timeouts.
- **Spec/SDK confusion:** read the pinned SDK source/docs and the MCP specification; write down what you learned in the ADR.

---

## PART 13 — Anti-patterns (do not do these)

- Building the next three tasks "while I'm here" in one commit.
- Hard-coding model names, URLs, limits, or IDs that belong in config.
- Adding a tool for every small variation instead of an `action`/`kind` enum within budget.
- Returning big JSON blobs or long paragraphs for speech.
- Trusting model output or retrieved text without validation.
- Using `datetime.now()` / `random` directly in logic that must be tested.
- Editing a deployed add-on's tool surface without the release checklist.
- Skipping the isolation test because "this tool is obviously safe."
- Writing tests that only assert "no exception was raised."
- Catching exceptions and returning `ok=true`.
- Storing quiz/session state in process memory.
- Leaving TODOs without an issue/task reference.
- Silent assumptions: if you assumed it, write it down.

---

## PART 14 — Command cheat sheet

```
make setup        # install deps (uv), pre-commit hooks
make dev          # docker compose up (app, worker, postgres, redis)
make migrate      # alembic upgrade heads
make migrate-check# up → down → up on a clean DB
make test         # unit + integration + contract
make lint         # ruff + mypy --strict + import-linter
make snapshot     # regenerate tests/snapshots/tools.json (intentional changes only)
make snapshot-check
make tunnel       # cloudflared tunnel to localhost:8000 (dev exposure for Alexa+)
make inspector    # MCP Inspector against the local server
```
Alexa AI CLI (confirm syntax against current official docs before use): `alexa-ai configure`, `alexa-ai new mcp --name "<name>" --locale <locale> --mcp-server-url "https://<domain>/mcp"`, `alexa-ai deploy`.

---

## PART 15 — Final instruction

Start now: run the **session protocol (Part 2)**, then begin **Stage A, step 1 (T0.1)**, and keep **T0.13** (documentation research and Private Preview access request) moving in parallel. Work one task at a time, prove each with tests, keep the repository green, record decisions and assumptions, and ask the human only for what you truly cannot determine yourself.
