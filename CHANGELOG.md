# Changelog

All notable changes to **Sahayak** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] - 2026-10-24

### Added
- **Multi-Add-On Deployment Profiles (Phase 13 / ADR 0016):**
  - Configurable deployment bundles: `study` (6 tools), `life` (12 tools), `work` (6 tools), `home` (8 tools), and `full` monolith (33 tools).
  - Add-on manifests under `alexa/<bundle>/addon.json` matching Alexa+ tool budget requirements.
  - Per-profile snapshot checks and contract testing harnesses.
- **Cross-Module Weekly Review (`weekly_review` MCP tool):**
  - Synthesizes student progress, habit streaks, budget adherence, and physical activity across modules into a fluid voice summary ($\le 300$ chars).
  - Strict compliance with published module APIs without cross-module database imports.
- **Feature Flags, User Preferences & Administrative CLI:**
  - `FeatureFlagStore` with kill-switches, hashed percentage rollouts (`hash(flag:user_id) % 100 < pct`), and per-user overrides.
  - `@check_feature_flag` decorator providing graceful voice error envelope (`error_code="feature_disabled"`).
  - `SettingsModule` and `settings` MCP tool (`status`, `enable_module`, `disable_module`).
  - Production admin CLI (`scripts/admin.py`) for user inspection, question quarantine, dead-letter replay, and audit trail generation (`core.audit_log`).
- **Local & Civic Information (Phase 12):**
  - `transit_status` tool with circuit-breaker-backed external transit API and fallback schedules.
  - `commodity_prices` tool with Agmarknet Mandi Open Data adapter, benchmark pricing, and attribution disclaimers.
  - `scheme_finder` tool with deterministic rules engine over 12+ national welfare schemes (PM-Kisan, Ayushman Bharat, PM SVANidhi, etc.).
- **Language Learning (Phase 11):**
  - `vocab` tool featuring word-of-the-day and SM-2 spaced repetition review.
  - `language_practice` tool with multi-turn conversations, LLM grammar evaluation, and turn caps.
- **Small Business (Phase 10):**
  - `orders` tool with customer order tracking and fulfillment state machine.
  - `ledger` tool with double-entry style customer balance bookkeeping and audit trails.
  - `sales_summary` tool with revenue analytics and concurrency-safe atomic inventory decrements.
- **Home & Family (Phase 9):**
  - `shared_list` tool with categorized items and family household coordination.
  - `chores` tool with chore schedules, overdue tracking, and member assignments.
  - `pantry_recipes` tool with perishable ingredient matching.
- **Career & Professional Development (Phase 8):**
  - `interview_practice` tool supporting mock interview drills and STAR-method scoring.
  - `application_tracker` tool managing job application pipelines and follow-up deadlines.
  - `career_practice` tool combining interview sessions and target role prep.
- **Health & Wellness (Phase 7):**
  - `health_log` tool for daily hydration, sleep, step tracking, and statutory disclaimers.
  - `health_summary` tool generating weekly health digests and hydration reminders.
- **Personal Finance (Phase 6):**
  - `expense_log` tool recording categorized transactions in integer minor units.
  - `budget` tool tracking category budget limits and variance.
  - `split_bill` tool implementing largest-remainder integer splitting for zero minor-unit loss.
  - `finance_report` tool delivering monthly financial summaries.
- **Productivity (Phase 5):**
  - `tasks` tool with due-date scheduling and priority queues.
  - `habits` tool supporting recurring habit streaks and freeze day tokens.
  - `notes` tool for voice memo capture and search.
  - `focus_timer` tool managing Pomodoro focus sessions.
  - `daily_briefing` tool providing morning multi-module briefings.
- **Academics (Phase 3):**
  - `quiz_start` and `quiz_answer` tools with deterministic answer matching and multi-turn state handles.
  - `flashcards` tool utilizing SuperMemo-2 (SM-2) scheduling.
  - `study_plan` tool providing daily study calendars and exam milestone planning.
  - `progress_report` and `topic_brief` tools.
  - Grounded question generation pipeline with Wikipedia client, LLM routing (Gemini + Groq), and quarantine validation.
- **Shared Infrastructure & Core Platform (Phases 0-2 & 4):**
  - Stateless Streamable HTTP MCP transport with JSON-RPC 2.0.
  - RFC 9728 OAuth protected-resource metadata and JWT validation with JWKS caching.
  - Automated security regression suite covering cross-user isolation across all 33 tools.
  - Reversible Alembic migrations with expand/contract architecture across all database schemas.
  - Docker containerization, Terraform cloud blueprints, Prometheus observability, and Grafana alerting definitions.

### Changed
- Reconciled PRD specification with final multi-addon profile architecture and 33 public MCP tools.
- Pinned all production dependencies with zero security vulnerabilities (`bandit` and `pip-audit` clean).
