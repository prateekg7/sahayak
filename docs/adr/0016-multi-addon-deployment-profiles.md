# 0016 — Multi-Add-On Deployment Profiles & Bundle Architecture

Status: Accepted
Date: 2026-10-24

## Context

Phase 13 Task 1 (`T13.1`) scales Sahayak across multiple specialized Alexa+ add-ons.

Key requirements and constraints:
1. **Tool Budget Limit & Cognitive Load**: Alexa+ performs optimal intent routing and tool selection when an individual add-on exposes between 5 and 12 focused tools (ADR 0002). Sahayak has 31 tools across 9 domains. Exposing 31 tools in a single add-on degrades LLM tool-calling accuracy and risks exceeding the platform tool budget.
2. **Single Codebase & Shared Identity**: Users must have a single account, single identity (`user_id`), and shared database across all add-ons. Progress in Study or spending in Life must not be isolated in separate siloed databases.
3. **Independent Deployability**: Each add-on must be capable of deploying independently via profile flags (`ENABLED_MODULES` or `DEPLOYMENT_PROFILE`), while supporting a unified development profile (`full`).

## Options Considered

1. **Monolithic Add-On (31 Tools)**:
   - *Pros*: Single deployment endpoint.
   - *Cons*: Violates ADR 0002 tool budget; creates prompt clutter and tool confusion in Alexa+ routing.
2. **Microservices in Separate Git Repositories**:
   - *Pros*: Isolated codebases.
   - *Cons*: Massive overhead, code duplication, distributed transactions, fractured identity, and synchronization complexity.
3. **Modular Monolith with Domain Bundles & Deployment Profiles**:
   - *Pros*: Single clean codebase, unified shared database, shared identity, zero network overhead between modules, and independent add-on endpoints configured via `DEPLOYMENT_PROFILE`.

## Decision

We adopt Option 3 with four specialized customer-facing add-on bundles plus a unified profile:

1. **Sahayak Study (`study`)**:
   - *Modules*: `academics`
   - *Tools (6)*: `quiz_start`, `quiz_answer`, `flashcards`, `study_plan`, `progress_report`, `topic_brief`.
   - *Endpoint*: `/mcp/study` (or `study.<domain>/mcp`).
2. **Sahayak Life (`life`)**:
   - *Modules*: `productivity`, `finance`, `health`
   - *Tools (11)*: `daily_briefing`, `focus_timer`, `habits`, `notes`, `tasks`, `split_bill`, `expenses`, `budget`, `finance_report`, `health_log`, `health_summary`.
   - *Endpoint*: `/mcp/life` (or `life.<domain>/mcp`).
3. **Sahayak Work (`work`)**:
   - *Modules*: `career`, `business`
   - *Tools (6)*: `application_tracker`, `interview_prep`, `career_practice`, `orders`, `customer_ledger`, `sales_summary`.
   - *Endpoint*: `/mcp/work` (or `work.<domain>/mcp`).
4. **Sahayak Home (`home`)**:
   - *Modules*: `home`, `language`, `local_info`
   - *Tools (8)*: `shared_list`, `chores`, `pantry_recipes`, `vocab`, `language_practice`, `transit_status`, `commodity_prices`, `scheme_finder`.
   - *Endpoint*: `/mcp/home` (or `home.<domain>/mcp`).
5. **Sahayak Full (`full`)**:
   - *Modules*: All 9 modules.
   - *Tools (31)*: Comprehensive development and unified staging endpoint.

### Shared Identity & Storage
- Single PostgreSQL database with module-specific schemas.
- Single Cognito/Auth0 OAuth 2.1 IdP. The same JWT token authenticates across all bundle endpoints with consistent `user_id`.

## Consequences

- Each add-on remains strictly within its 5–12 tool budget, ensuring high Alexa+ tool selection accuracy.
- Zero database duplication or distributed transaction overhead.
- CI verifies individual profile snapshots and contract suites alongside the complete repository regression.
