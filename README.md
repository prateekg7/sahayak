# Sahayak

<p align="center">
  <strong>Voice-First Everyday AI Assistant for Alexa+ & Model Context Protocol (MCP)</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12%2B-blue?logo=python&logoColor=white" alt="Python 3.12+">
  <img src="https://img.shields.io/badge/MCP%20Spec-2025--11--25-green" alt="MCP Spec">
  <img src="https://img.shields.io/badge/FastAPI-0.115%2B-009688?logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/Test%20Coverage-85%25%2B-brightgreen" alt="Coverage">
  <img src="https://img.shields.io/badge/Architecture-Clean%20%2F%20Modular-orange" alt="Clean Architecture">
  <img src="https://img.shields.io/badge/License-MIT-purple" alt="License">
</p>

---

## Table of Contents

- [Overview](#overview)
- [Architecture Highlights & Design Principles](#architecture-highlights--design-principles)
- [Deployment Profiles (ADR 0016)](#deployment-profiles-adr-0016)
- [Complete Tool Inventory (33 Tools)](#complete-tool-inventory-33-tools)
- [Repository Structure](#repository-structure)
- [Quick Start & Local Setup](#quick-start--local-setup)
  - [Prerequisites](#prerequisites)
  - [Option A: Local Virtualenv with `uv` (Recommended)](#option-a-local-virtualenv-with-uv-recommended)
  - [Option B: Full Containerized Stack (Docker Compose)](#option-b-full-containerized-stack-docker-compose)
- [Interactive Testing & Debugging](#interactive-testing--debugging)
  - [1. MCP Inspector UI](#1-mcp-inspector-ui)
  - [2. Cloudflare Tunnel (for Alexa+ Testing)](#2-cloudflare-tunnel-for-alexa-testing)
- [Alexa+ Add-on Package](#alexa-add-on-package)
- [Quality Gates & CI/CD](#quality-gates--cicd)
- [Documentation Index](#documentation-index)
- [License](#license)

---

## Overview

**Sahayak** (सहायक, *"Helper"* in Sanskrit and Hindi) is an enterprise-grade, privacy-first conversational assistant built on the **[Model Context Protocol (MCP)](https://modelcontextprotocol.io)** and tailored for **Amazon Alexa+**.

It delivers hands-free assistance across 10 life domains:
- **Academics & Study**: Dynamic quizzes, spaced-repetition flashcards (SuperMemo-2), exam schedules, and grounded knowledge overviews.
- **Productivity**: Daily morning briefings, task management, habit streaks, Pomodoro focus timers, quick voice notes, and weekly reviews.
- **Personal Finance**: Expense tracking, category budgets, shared bill splitting with settlement optimization, and financial reports.
- **Health & Wellness**: Logging water, workouts, sleep, vitals, and weekly wellness trend analysis.
- **Career**: Mock behavioral interviews with rubric scoring, job application pipelines, and resume elevator pitch practice.
- **Micro-Business**: Customer order management, small business credit/debit ledgers, and sales reports.
- **Home & Living**: Shared grocery lists, chore rotation schedules, and pantry-based recipe suggestions.
- **Languages**: Daily vocabulary acquisition (SM-2) and interactive conversational drills.
- **Local Information**: Public transit schedules, live agricultural mandi prices, and government scheme eligibility discovery.
- **Settings**: Assistant configuration, locale customization, and modular capability management.

---

## Architecture Highlights & Design Principles

```
                                    +-----------------------------+
                                    |     Alexa+ / MCP Client     |
                                    +--------------+--------------+
                                                   |
                                                   | Streamable HTTP POST /mcp (JSON-RPC 2.0)
                                                   v
+---------------------------------------------------------------------------------------------------+
| Sahayak Core (FastAPI / Starlette)                                                                |
|                                                                                                   |
|  [Security Middlewares]                                                                           |
|   ├── CORS Preflight Handler (OPTIONS /mcp -> 204 No Content)                                     |
|   ├── Origin & Host Header Validation                                                             |
|   ├── Request Size Limits & Rate Limiting                                                         |
|   └── OAuth 2.1 / OIDC Bearer Token Validator (RFC 9728 PRM)                                      |
|                                                                                                   |
|  [MCP Protocol Routing & Envelope]                                                                |
|   ├── Mcp-Session-Id & Stateless HTTP Transport                                                   |
|   ├── Voice-Friendly Sanitization (<= 300 chars, no markdown pipes, no raw URLs)                  |
|   └── Alexa Envelope: Top-level structuredContent + _meta.ui + Spoken content                     |
+-------------------------------------------------+-------------------------------------------------+
                                                  |
                     +----------------------------+----------------------------+
                     |                                                         |
                     v                                                         v
+--------------------+---------------------+     +-----------------------------+--------------------+
| Domain Modules (10 Isolated Packages)    |     | Shared Services & Infrastructure                 |
|                                          |     |                                                  |
| ├── academics    ├── career              |     | ├── Shared Identity & Users (user_id)            |
| ├── productivity ├── business            |     | ├── Shared Household Spaces                      |
| ├── finance      ├── home                |     | ├── Distributed Idempotency Service              |
| ├── health       ├── language            |     | ├── Outbox Event Dispatcher                      |
| ├── local_info   └── settings            |     | └── Multi-Provider LLM Gateway (Gemini / Groq)   |
|                                          |     |                                                  |
| Pattern: tools -> service -> domain      |     | Storage: PostgreSQL 16 (Async) + Redis 7 (Cache) |
+------------------------------------------+     +--------------------------------------------------+
```

### Key Architectural Tenets

1. **Stateless HTTP Transport**: Strictly implements the MCP Streamable HTTP specification. Sessions do not depend on sticky connections or in-memory server state.
2. **Layered Clean Architecture**: Every module strictly separates concerns:
   - `tools/`: MCP tool adapters declaring input schemas and delegating to services.
   - `service/`: Application orchestration and cross-domain events.
   - `domain/`: Pure business models and calculations (no I/O or framework dependencies).
3. **Cross-Module Boundaries**: Modules never cross-import each other's databases or internal classes. Communication occurs exclusively through `api.py` protocols or transactional outbox events.
4. **Voice-First Output Envelope**: All tool responses return dual representations:
   - `structuredContent`: Complete typed data for client rendering, cards, and UI hydration.
   - `content`: Voice-sanitized text ($\le 300$ characters, stripped of markdown tables, raw URLs, and emojis).
5. **Privacy Native (GDPR / CCPA)**: Built-in cascading data export (`export_user_data`) and permanent erasure (`delete_user_data`) across all schemas.

---

## Deployment Profiles (ADR 0016)

Exposing 30+ tools in a single Alexa add-on causes LLM cognitive overload and degrades tool selection accuracy. Sahayak implements **Deployment Profiles** ([ADR 0016](docs/adr/0016-multi-addon-deployment-profiles.md)) allowing the server to run as specialized 5–12 tool bundles or as a unified development instance:

| Profile | Target Domain | Active Modules | Tool Count | Primary Tools |
| :--- | :--- | :--- | :---: | :--- |
| **`study`** | Academic Mastery | `academics` | **6** | `quiz_start`, `quiz_answer`, `flashcards`, `study_plan`, `progress_report`, `topic_brief` |
| **`life`** | Everyday Flow | `productivity`, `finance`, `health` | **12** | `tasks`, `habits`, `notes`, `focus_timer`, `daily_briefing`, `weekly_review`, `expense_log`, `budget`, `split_bill`, `finance_report`, `health_log`, `health_summary` |
| **`work`** | Career & Business | `career`, `business` | **6** | `interview_practice`, `application_tracker`, `career_practice`, `orders`, `ledger`, `sales_summary` |
| **`home`** | Household & Local | `home`, `language`, `local_info` | **8** | `shared_list`, `chores`, `pantry_recipes`, `vocab`, `language_practice`, `transit_status`, `commodity_prices`, `scheme_finder` |
| **`full`** *(Dev)* | Comprehensive | *All 10 modules* | **33** | *All tools across the entire platform* |

> [!TIP]
> Control the active profile via the `DEPLOYMENT_PROFILE` environment variable (e.g. `DEPLOYMENT_PROFILE=full`).

---

## Complete Tool Inventory (33 Tools)

| Module | Tool Name | Voice Trigger / Example Utterance | Summary Description |
| :--- | :--- | :--- | :--- |
| **Academics** | [`quiz_start`](file:///src/sahayak/modules/academics/tools/quiz.py) | *"Alexa, quiz me on photosynthesis"* | Starts an interactive multiple-choice quiz on any topic with adaptive difficulty. |
| | [`quiz_answer`](file:///src/sahayak/modules/academics/tools/quiz.py) | *"Alexa, option B"* | Submits and grades an answer in an active quiz session. |
| | [`flashcards`](file:///src/sahayak/modules/academics/tools/flashcards.py) | *"Alexa, review my flashcards"* | Creates, reviews, grades (SM-2 algorithm), and lists spaced repetition cards. |
| | [`study_plan`](file:///src/sahayak/modules/academics/tools/study_plan.py) | *"Alexa, make a study plan for biology"* | Schedules day-by-day exam preparation milestones and daily study tasks. |
| | [`progress_report`](file:///src/sahayak/modules/academics/tools/progress.py) | *"Alexa, what are my weak topics?"* | Reports quiz accuracy, study streaks, weak subjects, and weekly stats. |
| | [`topic_brief`](file:///src/sahayak/modules/academics/tools/topic_brief.py) | *"Alexa, give me a brief on the Renaissance"* | Delivers a grounded, fact-checked spoken overview sourced from educational data. |
| **Productivity** | [`tasks`](file:///src/sahayak/modules/productivity/tools/tasks.py) | *"Alexa, add buy milk to my tasks due tomorrow"* | Creates, manages, filters, and completes personal to-do list items. |
| | [`habits`](file:///src/sahayak/modules/productivity/tools/habits.py) | *"Alexa, check in habit drink water"* | Tracks daily habits, completion streaks, and weekly consistency. |
| | [`notes`](file:///src/sahayak/modules/productivity/tools/notes.py) | *"Alexa, note that the garage code is 4321"* | Quick voice-capture memo pad with keyword search and audio playback. |
| | [`focus_timer`](file:///src/sahayak/modules/productivity/tools/focus.py) | *"Alexa, start a 25 minute focus session"* | Pomodoro focus session runner with interval alerts and completion logs. |
| | [`daily_briefing`](file:///src/sahayak/modules/productivity/tools/briefing.py) | *"Alexa, what is my day like?"* | Unified morning briefing aggregating tasks, habits, and study goals. |
| | [`weekly_review`](file:///src/sahayak/modules/productivity/tools/weekly_review.py) | *"Alexa, how did my week go?"* | End-of-week productivity retrospective combining tasks, study, and habits. |
| **Finance** | [`expense_log`](file:///src/sahayak/modules/finance/tools/expenses.py) | *"Alexa, log twenty dollars for lunch"* | Logs personal expenses with automatic category tagging and undo support. |
| | [`budget`](file:///src/sahayak/modules/finance/tools/budget.py) | *"Alexa, how much budget do I have left for dining?"* | Manages monthly category budgets and tracks real-time spending against caps. |
| | [`split_bill`](file:///src/sahayak/modules/finance/tools/split_bill.py) | *"Alexa, split ninety dollars with John and Sarah"* | Splits shared expenses, computes debt minimization, and logs settlements. |
| | [`finance_report`](file:///src/sahayak/modules/finance/tools/report.py) | *"Alexa, give me my monthly financial report"* | Spending breakdowns, upcoming bills, EMI reminders, and savings insights. |
| **Health** | [`health_log`](file:///src/sahayak/modules/health/tools/log.py) | *"Alexa, log two glasses of water"* | Logs daily wellness inputs: water, workouts, meals, sleep hours, and weight. |
| | [`health_summary`](file:///src/sahayak/modules/health/tools/summary.py) | *"Alexa, review my health this week"* | Summarizes wellness metrics, weekly averages, and medication schedules. |
| **Career** | [`interview_practice`](file:///src/sahayak/modules/career/tools/interview.py) | *"Alexa, interview me for a software engineer role"* | Interactive mock behavioral interview simulator with voice feedback scoring. |
| | [`application_tracker`](file:///src/sahayak/modules/career/tools/applications.py) | *"Alexa, add Amazon to my job applications"* | Tracks job application stages, interview dates, and follow-up deadlines. |
| | [`career_practice`](file:///src/sahayak/modules/career/tools/practice.py) | *"Alexa, help me improve my resume bullet"* | Formulates resume impact statements using the Google XYZ formula. |
| **Business** | [`orders`](file:///src/sahayak/modules/business/tools/orders.py) | *"Alexa, create an order for three coffee bags"* | Small business customer order intake, status tracking, and fulfillment. |
| | [`ledger`](file:///src/sahayak/modules/business/tools/ledger.py) | *"Alexa, record fifty dollars paid by Mike"* | Digital Khata / double-entry credit and debt ledger for micro-merchants. |
| | [`sales_summary`](file:///src/sahayak/modules/business/tools/sales.py) | *"Alexa, what were my sales today?"* | Daily revenue totals, top-selling items, and low-inventory warnings. |
| **Home** | [`shared_list`](file:///src/sahayak/modules/home/tools/shared_list.py) | *"Alexa, add olive oil to the grocery list"* | Collaborative household shopping lists with real-time check-off. |
| | [`chores`](file:///src/sahayak/modules/home/tools/chores.py) | *"Alexa, whose turn is it to do the dishes?"* | Household chore schedules with fair rotation algorithms and assignments. |
| | [`pantry_recipes`](file:///src/sahayak/modules/home/tools/pantry.py) | *"Alexa, what can I cook with eggs and spinach?"* | Inventories pantry ingredients and suggests zero-waste recipe options. |
| **Language** | [`vocab`](file:///src/sahayak/modules/language/tools/vocab.py) | *"Alexa, teach me a new Spanish word"* | Spaced repetition vocabulary builder with definitions and usage contexts. |
| | [`language_practice`](file:///src/sahayak/modules/language/tools/practice.py) | *"Alexa, practice ordering at a café in French"* | Conversational roleplay sessions with grammar hints and translations. |
| **Local Info** | [`transit_status`](file:///src/sahayak/modules/local_info/tools/transit.py) | *"Alexa, is the Blue Line running on time?"* | Real-time public transit status, schedules, and service disruption alerts. |
| | [`commodity_prices`](file:///src/sahayak/modules/local_info/tools/commodity.py) | *"Alexa, what is the price of wheat in Delhi mandi?"* | Daily agricultural market wholesale rates (mandi rates) and trends. |
| | [`scheme_finder`](file:///src/sahayak/modules/local_info/tools/schemes.py) | *"Alexa, find scholarship schemes for college students"* | Government citizen welfare and subsidy scheme eligibility discovery. |
| **Settings** | [`settings`](file:///src/sahayak/modules/settings/tools/settings.py) | *"Alexa, set my timezone to America/New_York"* | Assistant configuration, default preferences, and module enablement flags. |

---

## Repository Structure

```text
sahayak/
├── addon-package/                     # Alexa+ Add-on submission bundle
│   ├── addon.json                     # Store manifest (manifestVersion: 1.0)
│   └── assets/                        # Required icons (6 sizes) & carousel banner
├── alexa/                             # Deployment profile manifests (study, life, work, home)
├── docs/                              # Project documentation & runbooks
│   ├── adr/                           # 16 Architectural Decision Records (ADR 0001 - 0016)
│   ├── alexa/                         # Alexa+ certification, account linking, & test plans
│   ├── runbooks/                      # Production operational runbooks (disaster recovery, keys)
│   ├── architecture.md                # System architecture specification
│   ├── dev-guide.md                   # Comprehensive developer walkthrough
│   └── module-authoring.md            # Guide to authoring new modules from _template
├── infra/                             # Infrastructure as Code
│   ├── terraform/                     # AWS production infrastructure (ALB, ECS, RDS, Redis)
│   └── monitoring/                    # CloudWatch alerts & SLO specifications
├── migrations/                        # Alembic reversible async schema migrations
│   └── versions/                      # Expand-only database migration scripts
├── prompts/                           # Grounded LLM prompt templates (versioned)
├── scripts/                           # Maintenance & CI verification utilities
│   ├── snapshot_tools.py              # MCP tool schema snapshot generator & validator
│   ├── migrate_check.py               # Migration reversible up/down test runner
│   ├── smoke_test.py                  # End-to-end integration smoke runner
│   └── export_user.py                 # GDPR user data export utility
├── src/sahayak/                       # Application source root
│   ├── core/                          # Cross-cutting platform kernel
│   │   ├── auth/                      # OAuth 2.1, JWT RFC 9728 validator, middleware
│   │   ├── config.py                  # Pydantic v2 application settings
│   │   ├── envelope.py                # Alexa tool envelope & voice sanitization
│   │   ├── mcp_server.py              # Streamable HTTP MCP server & CORS routing
│   │   ├── module.py                  # Module protocol & dependency injection
│   │   ├── profiles.py                # Deployment profile definitions
│   │   ├── ratelimit.py               # Token bucket & sliding window rate limiters
│   │   └── security.py                # Security headers, origin checks, size limits
│   ├── modules/                       # 10 Domain capability modules
│   │   ├── _template/                 # Scaffold reference for new modules
│   │   ├── academics/                 # Quizzes, flashcards, study plans, briefs
│   │   ├── business/                  # Orders, ledger, sales summaries
│   │   ├── career/                    # Interview simulation, applications, practice
│   │   ├── finance/                   # Expenses, budgets, bill splitting, reports
│   │   ├── health/                    # Daily logs, weekly health summaries
│   │   ├── home/                      # Shopping lists, chores, pantry recipes
│   │   ├── language/                  # Vocabulary drills, conversational practice
│   │   ├── local_info/                # Transit delays, mandi prices, welfare schemes
│   │   ├── productivity/              # Tasks, habits, notes, Pomodoro, briefing
│   │   └── settings/                  # User profile & module configuration
│   ├── shared/                        # Shared cross-domain bounded contexts
│   │   ├── households/                # Shared household membership models
│   │   └── users/                     # Core identity & user provisioning
│   ├── container.py                   # Dependency injection container wiring
│   ├── main.py                        # FastAPI composition root & operational endpoints
│   └── worker.py                      # Arq async Redis background worker
├── tests/                             # Test suite (>85% code coverage)
│   ├── contract/                      # Tool schema snapshots & Alexa compliance tests
│   ├── integration/                   # Database, Redis, and multi-module integration
│   ├── load/                          # Locust and k6 latency benchmark suites
│   ├── security/                      # Rate limit, AST security, and input fuzzing
│   ├── snapshots/                     # Public tool JSON contract snapshots
│   └── unit/                          # Isolated business logic unit tests
├── docker-compose.yml                 # Local multi-service composition
├── LICENSE                            # MIT Open Source License
├── Makefile                           # Automated developer workflows
└── pyproject.toml                     # Python dependencies & tool configurations
```

---

## Quick Start & Local Setup

### Prerequisites

- **Python 3.12+**
- **[uv](https://docs.astral.sh/uv/)** (recommended ultra-fast package manager)
- **Docker & Docker Compose** (for PostgreSQL and Redis)
- **Node.js 20+** (optional, for running the MCP Inspector web UI)

---

### Option A: Local Virtualenv with `uv` (Recommended)

This is the fastest setup for local development with instant hot-reloading:

```bash
# 1. Clone the repository
git clone https://github.com/prateekg7/sahayak.git
cd sahayak

# 2. Install dependencies into virtual environment (.venv)
make setup

# 3. Create your local environment configuration
cp .env.example .env

# 4. Start backing databases (Postgres 16 and Redis 7) in the background
docker compose up -d postgres redis

# 5. Run database migrations
make migrate

# 6. Start the server with all 33 tools and auto-reload enabled
make run
```

The server is now live at:
- **API Root**: `http://localhost:8000`
- **Health Check**: `http://localhost:8000/healthz`
- **Prometheus Metrics**: `http://localhost:8000/metrics`
- **MCP Endpoint**: `http://localhost:8000/mcp`

*(Optional) Start the background worker for async tasks:*
```bash
PYTHONPATH=src uv run arq sahayak.worker.WorkerSettings
```

---

### Option B: Full Containerized Stack (Docker Compose)

To spin up the entire application inside Docker containers:

```bash
make dev
```

This compiles and orchestrates:
- `api`: FastAPI application serving `/mcp` on `http://localhost:8000`
- `worker`: Arq background worker processing outbox queues
- `postgres`: PostgreSQL 16 on `localhost:5432`
- `redis`: Redis 7 on `localhost:6379`

---

## Interactive Testing & Debugging

### 1. MCP Inspector UI

Test your tools visually with the official Model Context Protocol Inspector:

```bash
make inspector
```
This launches `@modelcontextprotocol/inspector` targeting `http://localhost:8000/mcp`. You can execute tool calls, inspect parameters, view validation errors, and observe latency.

> [!NOTE]
> If using MCP Inspector v2, connect to `http://localhost:8000/mcp` using the **Streamable HTTP** transport.

---

### 2. Cloudflare Tunnel (for Alexa+ Testing)

To expose your local running server to Amazon Alexa+ over a secure HTTPS endpoint:

```bash
make tunnel
```

`make tunnel` automatically runs:
```bash
cloudflared tunnel --protocol http2 --url http://localhost:8000
```
*(The `--protocol http2` flag bypasses UDP/QUIC blocks present on most home networks).*

Cloudflare will output a public HTTPS URL:
```text
+--------------------------------------------------------------------------------------------+
|  Your quick Tunnel has been created! Visit it at:                                          |
|  https://your-generated-subdomain.trycloudflare.com                                       |
+--------------------------------------------------------------------------------------------+
```

Your public Alexa+ MCP endpoint is:
`https://your-generated-subdomain.trycloudflare.com/mcp`

---

## Alexa+ Add-on Package

The [`addon-package/`](file:///Users/prateekgupta/Desktop/sahayak/addon-package/) directory contains the complete bundle required for publishing Sahayak as an official Alexa+ Add-on:

1. **[`addon.json`](file:///Users/prateekgupta/Desktop/sahayak/addon-package/addon.json)**: Manifest conforming to Alexa+ `manifestVersion: "1.0"`:
   - Name ($\le 30$ chars) and phonetic IPA pronunciation (`səˈhɑːjək`).
   - Short description ($\le 123$ chars) and comprehensive description.
   - Example voice invocation phrases.
   - Privacy Policy and Terms of Use HTTPS links.
   - Streamable HTTP HTTPS endpoint declaration.
2. **[`assets/icons/`](file:///Users/prateekgupta/Desktop/sahayak/addon-package/assets/icons/)**: Validated PNG light icons across all 6 mandatory dimensions:
   - `64x64`, `72x72`, `88x88`, `126x126`, `180x180`, `241x241`.
3. **[`assets/carousel/`](file:///Users/prateekgupta/Desktop/sahayak/addon-package/assets/carousel/)**: Promotional card image conforming to the required `600x900` resolution.

---

## Quality Gates & CI/CD

Sahayak enforces strict verification standards. All gates must pass before merging code:

```bash
# Run linting, formatting, type checking, and architecture import contracts
make lint

# Run full test suite with coverage enforcement (>= 85%)
make test

# Verify public tool schemas have not changed without snapshot updates
make snapshot-check

# Verify expand-only reversible migrations (up -> down -> up)
make migrate-check

# Run Bandit AST security scan and pip-audit vulnerability checks
make security
```

---

## Documentation Index

- **[Developer Guide](docs/dev-guide.md)**: Deep-dive local development, testing, and troubleshooting.
- **[Architecture Document](docs/architecture.md)**: System design, event outbox, and security boundaries.
- **[Module Authoring Guide](docs/module-authoring.md)**: Step-by-step tutorial on adding new modules from `_template`.
- **[Architectural Decision Records (ADRs)](docs/adr/index.md)**:
  - [ADR 0001: Language and Framework Selection](docs/adr/0001-language-and-framework.md)
  - [ADR 0002: Tool Budget & Cognitive Load](docs/adr/0002-tool-budget.md)
  - [ADR 0003: Account Linking & OAuth 2.1](docs/adr/0003-account-linking.md)
  - [ADR 0010: Latency & Response Size Budgets](docs/adr/0010-latency-and-response-size.md)
  - [ADR 0016: Multi-Add-On Deployment Profiles](docs/adr/0016-multi-addon-deployment-profiles.md)
- **[Security Threat Model](docs/security/threat-model.md)**: Threat vector analysis and mitigation matrix.
- **[Production Runbooks](docs/runbooks/)**:
  - [Disaster Recovery & Backup Restore](docs/runbooks/backup-restore.md)
  - [Zero-Downtime Deployment](docs/runbooks/deploy.md)
  - [Provider Outage Fallback](docs/runbooks/provider-outage.md)
  - [GDPR User Data Export & Erasure](docs/runbooks/user-data-request.md)

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
