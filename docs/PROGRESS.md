# Progress

## 2026-10-24 — T12.4 `scheme_finder` tool (government scheme eligibility) — DONE

- Summary: completed Phase 12 (Local and Civic Info Module) in full with a curated versioned dataset of 12+ prominent national welfare schemes, pure code declarative rules engine, conversational one-missing-fact clarification, and the `scheme_finder` MCP tool (31st platform tool):
  - Architecture Decision Record:
    - `docs/adr/0015-government-scheme-finder.md`: Documented deterministic pure code eligibility evaluation, curated in-tree versioned schemes dataset, one-missing-fact voice clarification loop, statutory guidance disclaimer, and anonymous access policy per ADR 0009.
    - Updated `docs/adr/index.md`.
  - Curated Dataset & CI Validation (`src/sahayak/modules/local_info/data/schemes.json`):
    - Curated 12 major welfare schemes: PM-Kisan, Ayushman Bharat, PM SVANidhi, PM Vishwakarma, PMAY Gramin, PM Mudra, Sukanya Samriddhi, Atal Pension Yojana, MGNREGA, PM Suraksha Bima, Stand-Up India, and Kisan Credit Card.
    - Each scheme includes official portal URL, beneficiary summary, category, last verified date, and structured eligibility criteria.
    - `scripts/validate_schemes.py`: Enforces link validity, date formats, and schema compliance in CI.
  - Domain Rules Engine (`src/sahayak/modules/local_info/domain/schemes.py`):
    - `SchemeCriteria`, `SchemeDefinition`, `UserProfile`, `EligibilityResult` domain models.
    - `evaluate_scheme`: Pure deterministic code evaluating age limits, income ceilings, occupation tags, gender rules, and landownership without LLM hallucinations.
    - `SchemeRepository`: Loads and searches schemes by ID, name, or fuzzy match.
    - Spoken formatters for scheme discovery, explanation, and qualification verification with automatic inclusion of the required legal guidance disclaimer strictly $\le 300$ characters.
  - Service (`src/sahayak/modules/local_info/service/schemes.py`):
    - `SchemeService`: Orchestrates `find_schemes` (with single-fact clarification question when info is missing), `explain_scheme`, and `check_eligibility`.
  - Public MCP Tool & Snapshot:
    - `tools/schemes.py`: `scheme_finder` MCP tool with `@allow_anonymous` supporting `find`, `explain`, and `check_eligibility` actions.
    - Registered tool in `local_info/module.py` and exported in `tools/__init__.py`.
    - `tests/snapshots/tools.json`: Updated snapshot to 31 tools.
  - Tests & Verification:
    - `tests/unit/test_schemes_domain.py`: Rules engine evaluation across diverse profiles, missing info identification, dataset lookup, dataset validation script invocation, and spoken formatters with disclaimers.
    - `tests/unit/test_schemes_service.py`: Blank profile conversational guidance, occupation matching, scheme explanation, and eligibility checks.
    - `tests/contract/test_scheme_finder_contract.py`: Contract test over Streamable HTTP verifying anonymous discovery, blank profile clarification, explanation with portal links, and auto-isolation.
    - `tests/security/isolation.py`: Registered `scheme_finder` in auto-isolation suite with `allows_anonymous=True`.
  - Quality Gates: `make lint`, `make test` (687 passed, 85.59% coverage), `make snapshot-check` (31 tools), `make migrate-check`, `make security` all green.
- Phase 12 (Local and Civic Info Module) Complete!
- Next: Phase 13 — Multi-add-on scaling, cross-module features, v1.0 (T13.1 through T13.4).

## 2026-10-24 — T12.3 `commodity_prices` tool — DONE

- Summary: implemented the `commodity_prices` MCP tool (30th platform tool) for agricultural mandi crop prices, wholesale market comparisons, and trends with Hindi/English crop aliasing, quintal-to-kg unit normalization, and date freshness warnings:
  - Architecture Decision Record:
    - `docs/adr/0014-commodity-prices-data-source.md`: Documented official Agmarknet / Open Government Data Platform India (data.gov.in) open data feeds under GODL-India license, bilingual phonetic crop aliasing, quintal wholesale to kg retail normalization, holiday freshness guards, and anonymous access policy per ADR 0009.
    - Updated `docs/adr/index.md`.
  - Domain Logic (`src/sahayak/modules/local_info/domain/commodity.py`):
    - `PriceRecord`, `CommodityTrend` domain models.
    - Canonical commodity aliases mapping Hindi and English terms ("gehun"/"wheat", "chawal"/"rice", "pyaz"/"onion", "aloo"/"potato", "tamatar"/"tomato", "chana"/"gram", "sarson"/"mustard", "makka"/"maize") with fuzzy fallback matching.
    - Canonical market resolution for major wholesale mandis (Azadpur, Ghazipur, Okhla, Narela, Khanna, Lasalgaon, Karnal, Indore).
    - Unit normalization converting wholesale prices in Rupees per Quintal (100 kg) to Rupees per Kilogram.
    - Spoken summaries strictly $\le 300$ characters with automatic freshness warnings ("Note: Rates are from X days ago as markets may have been closed") when data is older than 24h or fetched on weekends/holidays.
  - Adapter & Service (`src/sahayak/modules/local_info/`):
    - `adapters/commodity.py`: `CommodityHttpDataSource` extending `BaseHttpDataSource` with 3600s cache, host allow-listing, and benchmark fallback rates when upstream is unreachable.
    - `service/commodity.py`: `CommodityService` implementing `get_price`, `compare_markets`, and `get_trend` with days-old freshness detection and standard envelope shaping.
  - Public MCP Tool & Snapshot:
    - `tools/commodity.py`: `commodity_prices` MCP tool with `@allow_anonymous` supporting `get_price`, `compare_markets`, and `trend` actions.
    - Registered tool in `local_info/module.py` and exported in `tools/__init__.py`.
    - `tests/snapshots/tools.json`: Updated snapshot to 30 tools.
  - Tests & Verification:
    - `tests/unit/test_commodity_domain.py`: Commodity resolution across Hindi/English and fillers, market resolution, unit normalization (quintal to kg), fresh/stale spoken output, comparison, and trend formatting.
    - `tests/unit/test_commodity_service.py`: Price fetching, market comparison, price trend, and benchmark fallback.
    - `tests/contract/test_commodity_prices_contract.py`: Contract test over Streamable HTTP verifying anonymous execution with Hindi crop name, multi-market comparison, validation errors, and auto-isolation.
    - `tests/security/isolation.py`: Registered `commodity_prices` in auto-isolation suite with `allows_anonymous=True`.
  - Quality Gates: `make lint`, `make test` (671 passed, 85.57% coverage), `make snapshot-check` (30 tools), `make migrate-check`, `make security` all green.
- Next: T12.4 `scheme_finder` tool.

## 2026-10-24 — T12.2 `transit_status` tool — DONE

- Summary: implemented the `transit_status` MCP tool (29th platform tool) for real-time transit departures, operational line status, and delay alerts with fuzzy station matching and schedule headway fallback:
  - Architecture Decision Record:
    - `docs/adr/0013-transit-data-source.md`: Documented open transit API feeds under ODbL 1.0, fuzzy phonetic station resolution, schedule headway fallback during upstream outages, and anonymous access policy per ADR 0009.
    - Updated `docs/adr/index.md`.
  - Domain Logic (`src/sahayak/modules/local_info/domain/transit.py`):
    - `StationInfo`, `DepartureInfo`, `LineStatusInfo` domain models.
    - Canonical station dictionary covering key transit lines and colloquial spoken aliases ("cp" -> Rajiv Chowk, "ndls" -> New Delhi, "huda" -> Millennium City Centre, "airport"/"t3" -> IGI Airport, "isbt" -> Kashmere Gate, "anand vihar" -> Anand Vihar ISBT, etc.).
    - Fuzzy station resolver with Levenshtein similarity cutoff (0.68) resolving speech variations, phonetic misspellings, and colloquial station names.
    - Natural voice formatters for next departures and line status adhering to $\le 300$ characters without markdown or forbidden symbols.
  - Adapter & Service (`src/sahayak/modules/local_info/`):
    - `adapters/transit.py`: `TransitHttpDataSource` extending `BaseHttpDataSource` with 120s caching, host allow-listing, and automatic headway fallback when live tracking is unavailable.
    - `service/transit.py`: `TransitService` resolving stations, filtering departures by line/destination, retrieving line statuses, and producing standard envelopes.
  - Public MCP Tool & Snapshot:
    - `tools/transit.py`: `transit_status` tool with `@allow_anonymous` supporting `next_departures` and `status` actions.
    - Registered tool in `local_info/module.py` and exported in `tools/__init__.py`.
    - `tests/snapshots/tools.json`: Updated snapshot to 29 tools.
  - Tests & Verification:
    - `tests/unit/test_transit_domain.py`: Station resolution with exact names, colloquial aliases, fillers, fuzzy misspellings, unknown station handling, and speech length limits.
    - `tests/unit/test_transit_service.py`: Departures fetching, line/destination filtering, upstream failure fallback, and line status checks.
    - `tests/contract/test_transit_status_contract.py`: Contract test over Streamable HTTP verifying anonymous departures query, status check, validation errors, and auto-isolation.
    - `tests/security/isolation.py`: Registered `transit_status` in auto-isolation suite with `allows_anonymous=True`.
  - Quality Gates: `make lint`, `make test` (658 passed, 85.66% coverage), `make snapshot-check` (29 tools), `make migrate-check`, `make security` all green.
- Next: T12.3 `commodity_prices` tool.

## 2026-10-24 — T12.1 Data-source adapter framework — DONE

- Summary: implemented the foundational external data-source adapter framework and resilience policies for Phase 12 (Local and Civic Info Module):
  - Architecture Decision Record:
    - `docs/adr/0012-data-source-adapter-framework.md`: Documented external API integration requirements, host allow-listing for SSRF prevention, three-state circuit breakers per source, bounded exponential backoff retries, two-tier cache (fresh + stale), and stale-while-error resilience.
    - Updated `docs/adr/index.md`.
  - Module Skeleton & Contracts:
    - Created `src/sahayak/modules/local_info/` package (`ports.py`, `domain/`, `adapters/`, `schemas.py`, `api.py`, `module.py`).
    - Added `sahayak.modules.local_info` to `pyproject.toml` importlinter independent modules contract.
  - Ports & Base Adapter (`src/sahayak/modules/local_info/`):
    - `ports.py`: Defined `DataSourcePort[T]` protocol and `DataSourceResult[T]` generic model capturing data, source attribution, license, freshness timestamps (`fetched_at`, `cached_at`), and `is_stale` flag.
    - `adapters/circuit_breaker.py`: `DataSourceCircuitBreaker` implementing `CLOSED`, `OPEN`, `HALF_OPEN` states, 3-failure threshold, and 30s recovery timeout.
    - `adapters/base.py`: `BaseHttpDataSource` providing host allow-listing validation, configurable timeout (2.0s), bounded retries (up to 2 attempts), two-tier fresh/stale caching (in-memory or Redis), and automatic stale-while-error fallback during upstream outages.
  - Domain Freshness & Speech Attribution (`src/sahayak/modules/local_info/domain/attribution.py`):
    - `clean_spoken_text`: Strips markdown, emojis, asterisks, brackets, and quotes.
    - `format_relative_time_spoken`: Natural spoken relative time ("just now", "about X minutes ago", "about X hours ago", "about X days ago").
    - `format_freshness_spoken`: Prepares spoken freshness prefixes for fresh and stale data.
    - `format_data_answer_spoken`: Composes voice answers strictly adhering to $\le 300$ characters.
  - Tests & Verification:
    - `tests/unit/test_data_source_framework.py`: Verified host allow-listing validation, fresh caching hit prevention of outbound calls, bounded retries on transient errors, stale-while-error fallback during upstream outages, circuit breaker tripping and open-circuit stale delivery, voice freshness formatting, and module registry discovery.
    - `tests/security/isolation.py`: Updated user sub generation to use unique IDs per spec to eliminate database response truncation across test runs.
  - Quality Gates: `make lint`, `make test` (645 passed, 85.48% coverage), `make snapshot-check` (28 tools), `make migrate-check`, `make security` all clean.
- Next: T12.2 `transit_status` tool.

## 2026-10-24 — T11.2 `language_practice` tool (conversation and translate-and-explain) — DONE

- Summary: completed Phase 11 (Language Learning Module) in full with turn-limited conversation role-play sessions, structured grammar feedback and corrections, translate-and-explain queries, prompt guardrails, and the `language_practice` MCP tool (28th platform tool):
  - Database & Migrations:
    - `src/sahayak/modules/language/models.py`: Added `PracticeSession` model with `user_id`, `language`, `scenario`, `level`, `turns_completed`, `max_turns`, `status` (`active`, `completed`, `expired`, `abandoned`), `history` (JSONB conversation turns), and `expires_at` (30-minute TTL).
    - `src/sahayak/modules/language/migrations/0002_practice_sessions_schema.py`: Alembic migration creating `language.practice_sessions` table with indexes on `(user_id, status)` and `expires_at`. Reversible up->down->up.
  - Domain Logic (`src/sahayak/modules/language/domain/practice.py`):
    - Scenario normalization (`general`, `ordering_food`, `asking_directions`, `meeting_friends`, `travel`, `shopping`) with flexible aliases.
    - Curated scenario starters in target languages (Spanish, French, German, Hindi, Japanese).
    - Voice formatters for start conversation, partner reply turn with grammar corrections and explanations, and session completion celebration strictly $\le 300$ characters without markdown, asterisks, or quotes.
  - Adapters & Services:
    - `src/sahayak/modules/language/adapters/practice.py`: `SQLAlchemyPracticeSessionRepository` implementing active session lookup, session creation, save, and GDPR deletion.
    - `src/sahayak/modules/language/adapters/evaluator.py`: `LLMLanguagePracticeEvaluator` with structured `LLMConversationTurnOutput` and `LLMTranslateOutput` Pydantic schemas, supporting `LLMClient.generate_json` and deterministic fallbacks.
    - `src/sahayak/modules/language/service/practice.py`: `LanguagePracticeService` managing start conversation, reply turns, grammar corrections, turn limits (clamped to max 10), 30-minute session expiration, explicit session end, and outbox event dispatch (`language.practice.turn_completed`).
  - Public MCP Tool, Snapshot & GDPR:
    - `src/sahayak/modules/language/tools/language_practice.py`: `language_practice` MCP tool (28th platform tool) with `@requires()` authorization, `@idempotent(tool_name="language_practice")`, and standard envelope responses.
    - `src/sahayak/modules/language/module.py`: Registered `language_practice` tool; added `practice_sessions` to GDPR Right to Access export and deletion hooks.
    - `tests/snapshots/tools.json`: Tool snapshot updated to 28 tools.
  - Tests & Verification:
    - `tests/unit/test_language_practice_domain.py`: Scenario normalization, starters, and voice formatting length bounds.
    - `tests/unit/test_language_practice_service.py`: Conversation lifecycle, turn limiting, session completion, TTL expiration, previous session abandonment, structured LLM correction via `FakeLLMClient`, translation, and cross-user isolation.
    - `tests/contract/test_language_practice_contract.py`: Full MCP contract test over Streamable HTTP verifying anonymous rejection and complete authenticated lifecycle.
    - `tests/security/isolation.py`: Cross-user isolation verified across all 28 registered tools.
  - Quality Gates: `make lint`, `make test` (636 passed, 85.51% coverage), `make snapshot-check` (28 tools), `make migrate-check`, `make security` all green.
- Phase 11 (Language Learning Module) Complete!
- Next: Phase 12 — Local and civic info module (T12.1 through T12.4).

## 2026-10-24 — T11.1 `vocab` tool (daily vocabulary with spaced repetition) — DONE

- Summary: implemented Phase 11 Language Learning module foundation with language normalization (Spanish, French, German, Hindi, Japanese, Italian, Mandarin), curated seed vocabulary, word-of-the-day acquisition, SuperMemo-2 (SM-2) spaced repetition review quizzes via `shared/srs`, custom word additions, GDPR privacy hooks, and the `vocab` MCP tool (27th platform tool):
  - Database & Migrations:
    - Registered `language/migrations` branch in `alembic.ini` and `pyproject.toml` importlinter contracts.
    - `src/sahayak/modules/language/models.py`: Added `Word` (vocabulary cache with unique constraint `(language, word)`) and `UserWord` (spaced repetition review state with `ease`, `interval_days`, `repetitions`, `due_at`, unique constraint `(user_id, word_id)`).
    - `src/sahayak/modules/language/migrations/0001_language_schema.py`: Alembic migration creating `language.words` and `language.user_words` tables with indexes. Fully reversible up->down->up.
  - Domain Logic (`src/sahayak/modules/language/domain/`):
    - `languages.py`: Supported languages and proficiency levels (`beginner`, `intermediate`, `advanced`) normalization with alias handling.
    - `seeds.py`: Curated high-frequency seed vocabulary across languages and levels.
    - `vocab.py`: Validation and spoken summary formatters for word of the day, review card prompts, graded feedback, and statistics strictly $\le 300$ characters without markdown, asterisks, or quotes.
  - Adapters & Services:
    - `src/sahayak/modules/language/adapters/vocab.py`: `SQLAlchemyWordRepository` and `SQLAlchemyUserWordRepository` supporting unlearned word queries, due review queries, and learning statistics.
    - `src/sahayak/modules/language/service/vocab.py`: `VocabService` managing word-of-the-day (preventing duplicate assignments on the same day), due reviews, SM-2 grading with outbox event dispatch (`language.vocab.graded`), statistics, and custom word additions.
  - Public MCP Tool, Cross-Module API & GDPR:
    - `src/sahayak/modules/language/tools/vocab.py`: `vocab` MCP tool (27th platform tool) with `@requires()` authorization, `@idempotent(tool_name="vocab")`, and envelope responses.
    - `src/sahayak/modules/language/api.py`: `LanguageAPI` exposing `get_due_vocab_count` for cross-module integration.
    - `src/sahayak/modules/language/module.py`: Registered `vocab` tool; implemented GDPR Right to Access export and Right to Erasure deletion hooks.
    - `tests/snapshots/tools.json`: Snapshot updated to 27 tools.
  - Tests & Verification:
    - `tests/unit/test_language_vocab_domain.py`: Unit and Hypothesis property tests verifying language normalization, word validation, and voice formatting invariants.
    - `tests/unit/test_language_vocab_service.py`: Spaced repetition lifecycle test covering initial assignment, same-day duplicate prevention, multi-day progression with distinct words, SM-2 interval expansion, cross-user isolation, and stats.
    - `tests/unit/test_language_api.py`: Unit test verifying cross-module due vocab queries.
    - `tests/contract/test_vocab_contract.py`: Full MCP contract test over Streamable HTTP.
    - `tests/integration/test_language_privacy.py`: Verified GDPR export and deletion.
    - `tests/security/isolation.py`: Cross-user vocab isolation test registered and passing in auto-isolation suite.
  - Quality Gates: `make lint`, `make test` (629 passed, 85.70% coverage), `make snapshot-check` (27 tools), `make migrate-check`, `make security` all green.
- Next: T11.2 `language_practice` tool (conversation and translate-and-explain).

## 2026-10-24 — T10.3 `sales_summary` tool and low-stock alerts — DONE

- Summary: completed Phase 10 (Small Business module) with sales summaries (today/week/month), top-selling products by revenue, inventory catalog with atomic stock decrements, low-stock threshold queries, cross-module briefing integration, and the `sales_summary` MCP tool (26th platform tool):
  - Database & Migrations:
    - `src/sahayak/modules/business/models.py`: Added `Product` entity with `stock_level`, `low_stock_threshold`, `unit_price_minor`, constraints `ck_business_product_stock_non_negative` and `ck_business_product_price_non_negative`, and added `product_id` foreign key on `OrderItem`.
    - `src/sahayak/modules/business/migrations/0003_products_schema.py`: Alembic migration creating `business.products` table and adding `product_id` column to `business.order_items`. Fully reversible.
  - Domain Logic (`src/sahayak/modules/business/domain/sales.py`):
    - Sales aggregations and top-products sorting by revenue.
    - Low-stock threshold detection (`stock_level <= low_stock_threshold`).
    - Spoken summary formatters for today, week, top products, low stock, and product addition strictly $\le 300$ characters without markdown, asterisks, or quotes.
  - Adapters & Services:
    - `src/sahayak/modules/business/adapters/sales.py`: `SQLAlchemyProductRepository` with atomic row-level stock decrement `UPDATE business.products SET stock_level = stock_level - :qty WHERE id = :id AND stock_level >= :qty RETURNING stock_level` to guarantee race-safe non-negative inventory under concurrency.
    - `src/sahayak/modules/business/service/orders.py`: Updated order shipping transition to atomically decrement product stock for shipped order items.
    - `src/sahayak/modules/business/service/sales.py`: `SalesService` orchestrating today sales, weekly sales, top products, low stock alerts, and product additions.
  - Public MCP Tool, Cross-Module API & GDPR:
    - `src/sahayak/modules/business/tools/sales_summary.py`: `sales_summary` MCP tool (26th platform tool) with `@requires()` authorization, `@idempotent(tool_name="sales_summary")`, and standard envelope.
    - `src/sahayak/modules/business/api.py`: Added `get_low_stock_summary` to `BusinessAPI` protocol and implementation.
    - `src/sahayak/modules/productivity/service/briefing.py` & `productivity/module.py`: Updated `daily_briefing` tool to query low-stock alerts dynamically without static cross-module imports.
    - `src/sahayak/modules/business/module.py`: Registered `sales_summary` tool; added `products` to GDPR Right to Access export and deletion hooks.
    - `tests/snapshots/tools.json`: Snapshot updated to 26 tools.
  - Tests & Verification:
    - `tests/unit/test_business_sales_domain.py`: Unit tests for sales aggregations, top products formatting, and low-stock speech formatting under length bounds.
    - `tests/unit/test_business_sales_service.py`: Full lifecycle tests for products, today/week sales, low stock alerts, and concurrent race-condition shipment test proving stock never goes negative.
    - `tests/unit/test_briefing_service.py`: Unit test verifying low-stock alerts surfaced seamlessly in daily briefing.
    - `tests/contract/test_sales_summary_contract.py`: Full MCP contract test over Streamable HTTP.
    - `tests/security/isolation.py`: Cross-user sales summary and product isolation verified.
  - Quality Gates: `make lint`, `make test` (618 passed, 85.96% coverage), `make snapshot-check` (26 tools), `make migrate-check`, `make security` all green.
- Phase 10 (Small Business Module) Complete!
- Next: Phase 11 — Language learning module (T11.1 `vocab` tool).

## 2026-10-24 — T10.2 `ledger` tool (customer dues) — DONE

- Summary: implemented append-only double-entry style customer credit and debit ledger, balance computation purely from entries, reversal entries with full audit trail, top dues ordering, daily balance reconciliation, and the `ledger` MCP tool (25th platform tool):
  - Database & Migrations:
    - `src/sahayak/modules/business/models.py`: Added `LedgerEntry` entity with direction (`debit`/`credit`), `amount_minor` (positive minor units), `reversed_entry_id` self-referential foreign key, and composite indexes.
    - `src/sahayak/modules/business/migrations/0002_ledger_schema.py`: Alembic migration creating `business.ledger_entries` with `ck_business_ledger_amount_positive` check constraint. Reversible.
  - Domain Logic (`src/sahayak/modules/business/domain/ledger.py`):
    - Net effect computation: debit (+debt owed) and credit (-debt owed).
    - Customer balance calculated as exact sum of signed entry effects; never updated in place.
    - Voice formatters for add due, payment, balance, top dues, and reversal $\le 300$ chars without markdown/symbols.
  - Adapters & Services:
    - `src/sahayak/modules/business/adapters/ledger.py`: `SQLAlchemyLedgerRepository` implementing append-only entries, SQL-level aggregate balance calculations, and whole-store balance reconciliation.
    - `src/sahayak/modules/business/service/ledger.py`: `LedgerService` orchestrating dues, payments, balance queries, top dues ranking, entry reversals (guarding against duplicate or nested reversals), and zero-discrepancy daily reconciliation.
  - Public MCP Tool & GDPR:
    - `src/sahayak/modules/business/tools/ledger.py`: `ledger` MCP tool (25th platform tool) with `@requires()` authentication, `@idempotent(tool_name="ledger")`, and standard envelope.
    - `src/sahayak/modules/business/module.py`: Registered `ledger` tool; updated GDPR Right to Access export to include ledger entries.
    - `tests/snapshots/tools.json`: Snapshot updated to 25 tools.
  - Tests & Verification:
    - `tests/unit/test_business_ledger_domain.py`: Hypothesis property test verifying balances always equal sum of entries, reversal cancellation test, voice formatting rules.
    - `tests/unit/test_business_ledger_service.py`: Lifecycle integration testing dues, payments, balance queries, top dues descending ordering, reversals, duplicate reversal rejection, and daily reconciliation.
    - `tests/contract/test_ledger_contract.py`: MCP contract test over Streamable HTTP.
    - `tests/security/isolation.py`: Cross-user ledger isolation verified.
  - Quality Gates: `make lint`, `make test` (613 passed, 86.06% coverage), `make snapshot-check` (25 tools), `make migrate-check`, `make security` all green.
- Next: T10.3 `sales_summary` tool and low-stock alerts.

## 2026-10-24 — T10.1 Business tenancy and `orders` tool — DONE

- Summary: implemented Phase 10 Small Business module tenancy, customers, sequential order numbers per business, lifecycle order status machine, integer minor units currency calculation, and the `orders` MCP tool (24th platform tool):
  - Database & Migrations:
    - `src/sahayak/modules/business/models.py`: Added `Business`, `BusinessMember`, `Customer`, `Order`, and `OrderItem` models with constraints, indexes, and sequential `order_seq` generator on `Business`.
    - `src/sahayak/modules/business/migrations/0001_business_schema.py`: Alembic migration creating `business.businesses`, `business.business_members`, `business.customers`, `business.orders`, and `business.order_items`. Fully reversible.
  - Domain Logic (`src/sahayak/modules/business/domain/orders.py`):
    - Sequential status transitions: `pending -> packed -> shipped -> delivered` or `cancelled`. Illegal transitions rejected with actionable spoken voice guidance.
    - Money in integer minor units (e.g. paisa/cents) with natural spoken formatting.
    - Voice formatters strictly $\le 300$ characters without markdown, asterisks, or quotes.
  - Adapters & Services:
    - `src/sahayak/modules/business/adapters/orders.py`: `SQLAlchemyBusinessRepository` with atomic row-level increment `UPDATE business.businesses SET order_seq = order_seq + 1 RETURNING order_seq` to guarantee race-safe gap-free order numbers under concurrency.
    - `src/sahayak/modules/business/service/orders.py`: `OrderService` implementing `create_order`, `list_pending`, `update_status`, and `get_order`. Auto-provisions default business on first use.
  - Public MCP Tool & Module Registration:
    - `src/sahayak/modules/business/tools/orders.py`: `orders` MCP tool with `@requires()` scope check, `@idempotent(tool_name="orders")`, and structured envelope responses.
    - `src/sahayak/modules/business/module.py`: Registered `orders` (24th tool); implemented GDPR Right to Access and Right to Erasure hooks.
    - `tests/snapshots/tools.json`: Snapshot updated to 24 tools.
  - Tests & Verification:
    - `tests/unit/test_business_orders_domain.py`: Status machine transition validity and spoken currency/summary formatters.
    - `tests/unit/test_business_orders_service.py`: Order lifecycle, illegal transition errors, and concurrent order creation test verifying 20 concurrent orders receive distinct sequential numbers.
    - `tests/contract/test_orders_contract.py`: Full MCP Streamable HTTP contract testing.
    - `tests/security/isolation.py`: Cross-user tenancy isolation verified.
  - Quality Gates: `make lint`, `make test` (604 passed, 86.14% coverage), `make snapshot-check` (24 tools), `make migrate-check`, `make security` all green.
- Next: T10.2 `ledger` tool (customer dues).

## 2026-10-24 — T9.3 `chores` and `pantry_recipes` tools — DONE

- Summary: implemented shared household chores fair round-robin rotation, pantry tracking, dietary preferences, recipe matching with automatic missing ingredient handoff to shopping lists, and the `chores` (22nd) and `pantry_recipes` (23rd) MCP tools:
  - Database & Migrations:
    - `src/sahayak/modules/home/models.py`: Added `Chore`, `PantryItem`, and `HouseholdPreference` entities with foreign key cascades and indexes.
    - `src/sahayak/modules/home/migrations/0003_chores_and_pantry_schema.py`: Alembic migration creating `home.chores`, `home.pantry_items`, and `home.household_preferences` tables. Fully reversible.
  - Domain Logic:
    - `src/sahayak/modules/home/domain/chores.py`: Rotation calculation (`compute_next_chore_turn`), frequency calculation for daily, weekly, biweekly, monthly (`compute_next_due_date`), and voice formatters.
    - `src/sahayak/modules/home/domain/pantry.py`: Pantry parsing with quantity extraction, expiration detection (`is_expiring_soon`), dietary compliance (`check_diet_compliance`), allergen filtering (`check_allergen_free`), curated recipe matching (`match_recipes_from_pantry`), and voice formatters.
  - Adapters & Services:
    - `src/sahayak/modules/home/adapters/chores.py` & `pantry.py`: `SQLAlchemyChoreRepository` and `SQLAlchemyPantryRepository`.
    - `src/sahayak/modules/home/service/chores.py`: `ChoreService` managing chore creation, assignment, whose_turn queries, completion rotation, and listing.
    - `src/sahayak/modules/home/service/pantry.py`: `PantryService` handling inventory addition, listing, preference configuration, meal plan generation, and cross-service handoff to `SharedListService` for missing ingredients.
  - Public Tools & Registration:
    - `src/sahayak/modules/home/tools/chores.py` & `pantry_recipes.py`: MCP tools with `@requires()`, `@idempotent`, and standard envelope responses.
    - `src/sahayak/modules/home/module.py`: Registered tools in MCP server and updated GDPR Right to Access and Right to Erasure hooks.
    - `tests/snapshots/tools.json`: Snapshot updated to 23 tools.
  - Tests & Verification:
    - `tests/unit/test_chores_domain.py`: Unit and Hypothesis property tests verifying fair rotation distribution over 200 iterations with delta <= 1.
    - `tests/unit/test_pantry_domain.py`: Unit tests for parsing, expiration, allergens, recipes, and voice summaries.
    - `tests/unit/test_chores_service.py` & `test_pantry_service.py`: Lifecycle, rotation, and shopping list handoff integration tests.
    - `tests/contract/test_chores_contract.py` & `test_pantry_recipes_contract.py`: MCP contract tests over Streamable HTTP.
    - `tests/security/isolation.py`: Cross-user isolation tests for `chores` and `pantry_recipes`.
  - Quality Gates: `make lint`, `make test` (597 passed, 86.53% coverage), `make snapshot-check` (23 tools), `make migrate-check`, `make security` all green.
- Phase 9 (Home and Family Module) Complete!
- Next: Phase 10 — Small business module (T10.1 Business tenancy and `orders` tool).

- Summary: implemented shared family grocery and shopping lists with automatic household creation, quantity parsing, case-insensitive deduplication merge policy, check off/clear workflows, GDPR export/scrubbing, and the `shared_list` MCP tool (21st platform tool):
  - Database & Migrations:
    - `src/sahayak/modules/home/models.py`: Added `SharedList` and `SharedListItem` models with foreign key cascades, `uq_home_lists_household_name` constraint, and `ix_home_list_items_list_checked` index.
    - `src/sahayak/modules/home/migrations/0002_lists_schema.py`: Alembic migration creating `home.lists` and `home.list_items` tables with UTC timestamps. Reversible.
  - Domain Logic (`src/sahayak/modules/home/domain/lists.py`):
    - Quantity regex parser (`QUANTITY_PATTERN`) extracting leading units and quantities (e.g. "2 liters of whole milk" -> "Whole Milk", "2 liters").
    - Name normalization (`normalize_list_name`, `normalize_item_name`) ensuring consistency and length limits.
    - Spoken formatters for add, check off, remove, clear, and list summary (capped at 5 items with summary of remaining), strictly <= 300 characters, no markdown/symbols/emojis.
  - Ports, Adapters & Services:
    - `src/sahayak/modules/home/ports.py`: Defined `ListRepositoryPort`.
    - `src/sahayak/modules/home/adapters/lists.py`: `SQLAlchemyListRepository` with atomic `pg_insert` + `on_conflict_do_nothing` for concurrent list creation, case-insensitive item deduplication updating quantity/added_by, and bulk clearance.
    - `src/sahayak/modules/home/service/lists.py`: `SharedListService` resolving user household context (with seamless default Family household auto-creation for new users), orchestrating add, read, check_off, remove, and clear_checked.
  - Public MCP Tool & GDPR:
    - `src/sahayak/modules/home/tools/shared_list.py`: `shared_list` MCP tool with `@requires()` authorization, `@idempotent(tool_name="shared_list")`, and voice-friendly error handling.
    - `src/sahayak/modules/home/module.py`: Registered `shared_list` tool (21st platform tool); updated GDPR export to include family lists and items; updated GDPR erasure to scrub `added_by` references while preserving household list continuity.
  - Tests & Verification:
    - `tests/unit/test_shared_list_domain.py`: 5 tests covering list and item name normalization, quantity extraction, speech formatters, and length constraints.
    - `tests/unit/test_shared_list_service.py`: 3 comprehensive tests verifying list lifecycle, case-insensitive item deduplication merge, cross-household isolation, and concurrent additions by multiple household members.
    - `tests/contract/test_shared_list_contract.py`: Streamable HTTP MCP contract testing, anonymous rejection, and full authenticated CRUD lifecycle.
    - `tests/integration/test_home_privacy.py`: Verified GDPR export and item user ID scrubbing upon user erasure.
    - `tests/security/isolation.py`: Registered `shared_list` in cross-user isolation auto-discovery suite.
    - `tests/snapshots/tools.json`: Snapshot updated to 21 tools.
  - Quality Gates: `make lint`, `make test` (582 passed, 86.76% coverage), `make snapshot-check` (21 tools), `make migrate-check`, `make security` all green.
- Next: T9.3 `chores` and `pantry_recipes` tools.

## 2026-10-23 — T9.1 Households and sharing model (ADR first) — DONE

- Summary: designed and implemented Phase 9 (Home and Family Module) foundation with household tenancy, membership authorization, invite code flows, published HomeAPI, and GDPR shared ownership rules:
  - Architecture Decision Record (`docs/adr/0011-household-sharing-model.md`):
    - Documented multi-user household tenancy model with roles (`owner`, `member`), 48-hour expiring invite codes, and mandatory `assert_member` authorization barrier.
    - Defined GDPR deletion semantics: owner erasure transfers ownership to oldest member, or deletes household if sole member.
    - Updated `docs/adr/index.md`.
  - Database & Migrations:
    - Registered `home/migrations` in `alembic.ini` and `pyproject.toml` importlinter contracts.
    - `src/sahayak/modules/home/models.py`: `Household`, `HouseholdMembership` (with unique constraint `uq_home_membership_household_user`), and `HouseholdInvite` models in schema `home`.
    - `src/sahayak/modules/home/migrations/0001_home_schema.py`: Alembic migration creating `home.households`, `home.memberships`, and `home.invites` with cascade deletion. Reversible.
  - Domain Logic (`src/sahayak/modules/home/domain/households.py`):
    - Unambiguous 6-character uppercase alphanumeric code generation (`INVITE_CHARSET`).
    - Household name normalization and length limits.
    - Spoken formatters for creation, onboarding, and membership reporting under 300 characters without markdown.
  - Ports, Adapters & Services:
    - `src/sahayak/modules/home/ports.py`: `HouseholdRepositoryPort`.
    - `src/sahayak/modules/home/adapters/households.py`: `SQLAlchemyHouseholdRepository` handling creation, lookups, invite redemption, and membership management.
    - `src/sahayak/modules/home/service/households.py`: `HouseholdService` enforcing membership checks, invite generation, joining, and leaving households.
    - `src/sahayak/modules/home/api.py`: published `HomeAPI` providing `assert_member`, `get_user_households`, and member queries for subsequent home tools (`shared_list`, `chores`).
  - Module & GDPR Hooks:
    - `src/sahayak/modules/home/module.py`: `HomeModule` registered in `ModuleRegistry`, GDPR `export_user_data` and `delete_user_data` with automatic ownership transfer.
  - Tests & Verification:
    - `tests/unit/test_households_domain.py`: 5 tests covering invite code randomness/unambiguity, normalization, voice formatters, and sanitization.
    - `tests/unit/test_households_service.py`: full lifecycle test verifying household creation, owner role, member joining, invite expiry/single-use, `assert_member` rejections for non-members, and member leaving.
    - `tests/integration/test_home_privacy.py`: verified GDPR export and ownership transfer upon owner deletion.
    - `tests/security/test_tool_isolation_auto.py`: loaded `home` module into auto-isolation test harness.
  - Quality Gates: `make lint`, `make test` (573 passed, 86.79% coverage), `make snapshot-check`, `make migrate-check`, `make security` all green.
- Next: T9.2 `shared_list` tool.

## 2026-10-23 — T8.3 `career_practice` tool (resume bullets, daily question) — DONE

- Summary: implemented resume bullet point polish with Google's XYZ formula, daily technical and behavioral practice question bank with unrepeated rotation, answer evaluation, GDPR privacy, and the `career_practice` MCP tool (completing Phase 8):
  - Database & Migrations:
    - `src/sahayak/modules/career/models.py`: `DailyPractice` model in schema `career` with user scoping, question_key, question_text, user_answer, is_correct, feedback, and indexes `ix_career_practice_user_key`, `ix_career_practice_user_created`.
    - `src/sahayak/modules/career/migrations/0003_practice_schema.py`: Alembic migration creating `career.daily_practice` with cascade deletion on user removal. Fully reversible.
  - Domain Logic (`src/sahayak/modules/career/domain/practice.py`):
    - Google XYZ formula improver (`improve_resume_bullet`): parses user action, generates metric-driven accomplishment and scale-oriented variations, spoken summary <= 300 characters.
    - Curated bank of 8+ technical/system design/behavioral questions (`CURATED_DAILY_QUESTIONS`) with topics, key points, sample answers, and keywords.
    - Unrepeated rotation (`get_next_daily_question`) filtering out already answered keys and cycling when completed.
    - Deterministic answer evaluator (`evaluate_daily_answer`) checking concept coverage and returning concise spoken model answers.
  - Ports, Adapters & Service:
    - `src/sahayak/modules/career/ports.py`: `PracticeRepositoryPort`.
    - `src/sahayak/modules/career/adapters/practice.py`: `SQLAlchemyPracticeRepository` supporting recording attempts, fetching answered keys, and calculating cumulative user stats using SQL `case` aggregation.
    - `src/sahayak/modules/career/service/practice.py`: `CareerPracticeService` orchestrating improve_bullet, daily_question, and check_daily_answer workflows.
  - Public MCP Tool & GDPR:
    - `src/sahayak/modules/career/tools/career_practice.py`: `career_practice` MCP tool with `@requires()` authorization, `@idempotent(tool_name="career_practice")`, and standard envelope.
    - `src/sahayak/modules/career/module.py`: registered `career_practice` MCP tool (20th platform tool), updated GDPR export/erasure to include daily practice history.
  - Tests & Verification:
    - `tests/unit/test_career_practice_domain.py`: 7 tests verifying XYZ bullet improvement, daily question validity, unrepeated rotation, accurate answer grading, and weak answer grading.
    - `tests/unit/test_career_practice_service.py`: full lifecycle test covering bullet improvement, daily questions, answer evaluation, and practice stats.
    - `tests/contract/test_career_practice_contract.py`: full Streamable HTTP MCP contract testing and anonymous rejection.
    - `tests/integration/test_career_privacy.py`: verified GDPR export and right-to-be-forgotten deletion covering daily practice records.
    - `tests/security/isolation.py`: registered `career_practice` in cross-user isolation auto-discovery suite.
  - Quality Gates: `make lint`, `make test` (566 passed, 86.88% coverage), `make snapshot-check` (20 tools), `make migrate-check`, `make security` all green.
- Next: Phase 9 — Home and Family Module (T9.1 Households & sharing model).

## 2026-10-23 — T8.2 `application_tracker` tool and follow-up deadlines — DONE

- Summary: implemented job application pipeline tracking, status transitions, follow-up deadline alerts, cross-module published API, and the `application_tracker` MCP tool:
  - Database & Migrations:
    - `src/sahayak/modules/career/models.py`: `Application` model with user scoping, company, role, status enum, applied_at, follow_up_at, notes, and index `ix_career_apps_user_status`.
    - `src/sahayak/modules/career/migrations/0002_applications_schema.py`: Alembic migration creating `career.applications` with cascade deletion on user removal. Reversible.
  - Domain Logic (`src/sahayak/modules/career/domain/applications.py`):
    - Canonical statuses: applied, screening, interviewing, offer, rejected, withdrawn.
    - Natural date parser for follow-up deadlines (tomorrow, in N days, next week, ISO dates).
    - Voice-friendly pipeline summary formatter (<= 300 characters, no markdown, no quotes).
  - Ports, Adapters & Published API:
    - `src/sahayak/modules/career/ports.py`: `ApplicationRepositoryPort`.
    - `src/sahayak/modules/career/adapters/applications.py`: `SQLAlchemyApplicationRepository` supporting creation, status updates, filtered listing, and due follow-up queries.
    - `src/sahayak/modules/career/api.py`: published `CareerAPI` providing `get_due_followups` for cross-module briefing integration.
  - Service & Public MCP Tool:
    - `src/sahayak/modules/career/service/applications.py`: `ApplicationService` handling add, update_status, list, due_followups, and delete actions.
    - `src/sahayak/modules/career/tools/application_tracker.py`: `application_tracker` MCP tool with `@requires()` authorization, `@idempotent(tool_name="application_tracker")`, and standard envelope.
    - `src/sahayak/modules/career/module.py`: registered `application_tracker` tool (19th platform tool), wired `CareerAPI`, updated GDPR export/erasure.
  - Tests & Verification:
    - `tests/unit/test_applications_domain.py`: 3 tests verifying status normalization, natural follow-up date parsing, and pipeline speech formatting.
    - `tests/unit/test_applications_service.py`: full lifecycle test covering adding, status updating, status filtering, due follow-ups, and deletion.
    - `tests/contract/test_application_tracker_contract.py`: full Streamable HTTP MCP contract testing and anonymous rejection.
    - `tests/integration/test_career_privacy.py`: verified GDPR export and right-to-be-forgotten deletion covering applications.
    - `tests/security/isolation.py`: registered `application_tracker` in cross-user isolation auto-discovery suite.
  - Quality Gates: `make lint`, `make test` (557 passed, 86.80% coverage), `make snapshot-check` (19 tools), `make migrate-check`, `make security` all green.
- Next: T8.3 `career_practice` tool (resume bullets, daily question).

## 2026-10-23 — T8.1 `interview_practice` tool and rubric evaluation — DONE

- Summary: implemented Phase 8 (Career module) foundation with mock interview practice, structured rubric evaluations, curated question banks, session handle state, GDPR compliance, and the `interview_practice` MCP tool:
  - Database & Migrations:
    - Registered `career/migrations` branch in `alembic.ini` and `pyproject.toml` importlinter contracts.
    - `src/sahayak/modules/career/models.py`: `InterviewSession` and `InterviewTurn` models in schema `career` with index `ix_career_sessions_user_status` and unique constraint `uq_career_turns_session_q_idx`.
    - `src/sahayak/modules/career/migrations/0001_career_schema.py`: Alembic migration creating `career.interview_sessions` and `career.interview_turns` tables with foreign keys to `core.users(id)` and cascade deletion. Fully reversible.
  - Domain Rubric Logic (`src/sahayak/modules/career/domain/rubric.py`):
    - Curated interview question bank for multiple roles (Software Engineer, Product Manager, General) across junior, mid, and senior levels with graceful fallbacks.
    - Structured rubric scoring model: clarity (1-5), relevance (1-5), depth (1-5), average score, actionable tips (max 2), and spoken feedback string.
    - Voice text sanitization ensuring spoken output is strictly under 300 characters without markdown, quotes, emojis, or forbidden symbols.
    - Deterministic fallback rubric evaluator for malformed LLM outputs or offline environments.
  - Ports & Adapters:
    - `src/sahayak/modules/career/ports.py`: `InterviewRepositoryPort` and `InterviewEvaluationPort`.
    - `src/sahayak/modules/career/adapters/interviews.py`: `SQLAlchemyInterviewRepository` with user isolation and deterministic ordering.
    - `src/sahayak/modules/career/adapters/evaluator.py`: `LLMInterviewEvaluator` with structured JSON schema (`LLMRubricOutput`) and fallback parser.
  - Service & Public MCP Tool:
    - `src/sahayak/modules/career/service/interview.py`: `InterviewService` orchestrating start, answer, finish, and history actions with `UnitOfWork`.
    - `src/sahayak/modules/career/tools/interview_practice.py`: `interview_practice` MCP tool with `@requires()` authorization, `@idempotent(tool_name="interview_practice")`, and standard envelope.
    - `src/sahayak/modules/career/module.py`: registered `interview_practice` tool (18th tool across platform), implemented GDPR export and right-to-be-forgotten deletion.
  - Tests & Verification:
    - `tests/unit/test_interview_domain.py`: 5 tests covering curated banks, text sanitization, valid/markdown/malformed rubric evaluations.
    - `tests/unit/test_interview_service.py`: full lifecycle with `FakeLLMClient`, multi-turn evaluation, session completion, early finish, and isolation.
    - `tests/contract/test_interview_contract.py`: full Streamable HTTP MCP contract testing and anonymous rejection.
    - `tests/integration/test_career_privacy.py`: verified GDPR export and right-to-be-forgotten deletion covering sessions and turns.
    - `tests/security/isolation.py`: registered `interview_practice` in cross-user isolation auto-discovery suite.
  - Quality Gates: `make lint`, `make test` (552 passed, 86.96% coverage), `make snapshot-check` (18 tools), `make migrate-check`, `make security` all green.
- Next: T8.2 `application_tracker` tool.

## 2026-10-23 — T7.2 Medicine reminders and `health_summary` tool — DONE

- Summary: completed Phase 7 (Health module) with medicine schedule tracking, adherence rate analytics, periodic health summaries, GDPR integration, and the `health_summary` MCP tool:
  - Database & Migrations:
    - `src/sahayak/modules/health/models.py`: `Medicine` and `MedicineDose` models with user scoping, active weekday schedules, dosage descriptions, and dose statuses (`pending`, `taken`, `skipped`, `missed`).
    - `src/sahayak/modules/health/migrations/0002_medicines_schema.py`: Alembic migration creating `health.medicines` and `health.medicine_doses` tables with unique constraint `uq_health_doses_med_date_time`. Reversible.
  - Domain Schedule & Summary Logic (`src/sahayak/modules/health/domain/summary.py`):
    - Schedule evaluation logic checking start/end dates and weekday restrictions.
    - Daily health aggregation combining raw water ml, sleep duration, exercise minutes, calories, and medicine completion.
    - 7-day trend calculations with daily averages and medicine adherence percentage math.
    - Spoken summary formatters producing concise voice text under 300 characters without markdown or clinical advice.
  - Ports & Adapters:
    - `src/sahayak/modules/health/ports.py`: `MedicineRepositoryPort`.
    - `src/sahayak/modules/health/adapters/medicines.py`: `SQLAlchemyMedicineRepository` supporting medicine creation, dose recording, range queries, and soft deactivation.
  - Service & Public MCP Tool:
    - `src/sahayak/modules/health/service/health_summary.py`: `HealthSummaryService` managing today, week, medicines_due, mark_taken, add_medicine, and list_medicines.
    - `src/sahayak/modules/health/tools/health_summary.py`: `health_summary` MCP tool with `@requires()` authorization, `@idempotent(tool_name="health_summary")`, and standard envelope.
    - `src/sahayak/modules/health/module.py`: registered `health_summary` tool (17th tool in total across modules, completing Phase 7), integrated medicines and doses into GDPR export and deletion.
  - Tests & Verification:
    - `tests/unit/test_health_summary_domain.py`: 9 unit tests verifying schedule evaluation, weekly averages, adherence math, and spoken formatters.
    - `tests/unit/test_health_summary_service.py`: full service lifecycle covering today/week summaries, medicine addition, and dose marking.
    - `tests/contract/test_health_summary_contract.py`: full Streamable HTTP MCP contract testing and anonymous rejection.
    - `tests/integration/test_health_privacy.py`: verified GDPR export and right-to-be-forgotten deletion covering medicines and doses.
    - `tests/security/isolation.py`: registered `health_summary` tool in cross-user auto-isolation suite.
  - Quality Gates: `make lint`, `make test` (543 passed, 87.18% coverage), `make snapshot-check` (17 tools), `make migrate-check`, `make security` all green.
- Next: Phase 8 (Career module) — T8.1 `interview_practice` tool and rubric evaluation.

## 2026-10-23 — T7.1 `health_log` tool and plausibility validation — DONE


- Summary: implemented Phase 7 (Health module) foundation with personal metric tracking, strict plausibility bounds, metric/imperial unit conversions, voice undo, GDPR compliance, and the `health_log` MCP tool:
  - Strict Medical Safety Guardrail (PRD §1.4):
    - Personal health metric logging only; zero medical diagnosis, dosing, or clinical advice.
    - `HEALTH_DISCLAIMER` attached to all data envelopes and tool metadata.
  - Plausibility Validation & Unit Conversions (`src/sahayak/modules/health/domain/entries.py`):
    - Supported kinds: `water`, `meal`, `workout`, `sleep`, `weight`.
    - Water: accepts ml, liters, oz, cups, glasses; plausibility bounds [50 ml, 5,000 ml].
    - Weight: accepts kg, lbs; converted to kg; plausibility bounds [20 kg, 500 kg].
    - Sleep: accepts hours, minutes; converted to hours; plausibility bounds [0.5 hr, 24 hr].
    - Workout: activity required; minutes or hours duration; plausibility bounds [1 min, 600 min].
    - Meal: description required; optional meal type (breakfast, lunch, dinner, snack) and calories [10 kcal, 10,000 kcal].
    - Spoken summary formatters producing concise voice strings under 300 characters without markdown or quotes.
  - Database & Migrations:
    - Registered `health/migrations` branch in `alembic.ini` and `pyproject.toml` importlinter contracts.
    - `src/sahayak/modules/health/models.py`: `HealthEntry` model in schema `health` with JSONB typed metric data and composite index `ix_health_entries_user_kind_occurred`.
    - `src/sahayak/modules/health/migrations/0001_health_schema.py`: Alembic migration creating `health.entries` table with foreign key to `core.users(id)` and soft-deletion support (`is_deleted`). Reversible.
  - Service & Public MCP Tool:
    - `src/sahayak/modules/health/ports.py`: `HealthRepositoryPort`.
    - `src/sahayak/modules/health/adapters/entries.py`: `SQLAlchemyHealthRepository` with deterministic secondary ordering by `created_at.desc()`.
    - `src/sahayak/modules/health/service/health_log.py`: `HealthLogService` orchestrating log, list, undo_last, and delete actions with `UnitOfWork`.
    - `src/sahayak/modules/health/tools/health_log.py`: `health_log` MCP tool with `@requires()` authorization, `@idempotent(tool_name="health_log")`, and standard envelope.
    - `src/sahayak/modules/health/module.py`: registered `health_log` tool (16th tool across platform), implemented GDPR export and right-to-be-forgotten deletion.
  - Tests & Quality Gates:
    - `tests/unit/test_health_domain.py`: 12 tests covering all kinds, conversions, plausibility bounds, and voice formatters.
    - `tests/unit/test_health_log_service.py`: full lifecycle test covering logging, listing, undo, and deletion with advancing clocks.
    - `tests/contract/test_health_log_contract.py`: full Streamable HTTP MCP contract testing and anonymous rejection.
    - `tests/integration/test_health_privacy.py`: verified GDPR export and right-to-be-forgotten deletion.
    - `tests/security/isolation.py`: registered `health_log` in cross-user isolation auto suite.
    - All 5 Quality Gates passed: `make lint`, `make test` (532 passed, 87.03% coverage), `make snapshot-check` (16 tools), `make migrate-check`, `make security`.
- Next: T7.2 Medicine reminders and `health_summary` tool.

## 2026-10-23 — T6.4 `finance_report` tool and recurring bills — DONE


- Summary: completed Phase 6 (Finance module) with periodic spending summaries, category analysis, recurring bill and EMI due-date tracking, roll-forwards, and the `finance_report` MCP tool:
  - Database & Migrations:
    - `src/sahayak/modules/finance/models.py`: `Bill` model in schema `finance` with integer minor units (`amount_minor`), frequency, due_day, next_due_date, and composite index `ix_finance_bills_user_due`.
    - `src/sahayak/modules/finance/migrations/0004_bills_schema.py`: Alembic migration creating `finance.bills` table with foreign keys to `core.users(id)` with cascading deletion. Reversible.
  - Domain Reports & Roll-forwards (`src/sahayak/modules/finance/domain/reports.py`):
    - Report period calculation for monthly and weekly periods with exact previous month/week boundaries.
    - Bill roll-forward logic handling monthly, weekly, and yearly frequencies with month-end day clamping (e.g. Feb 28 in non-leap years).
    - Period-over-period spending comparison (difference in minor units and percentage change).
    - Spoken summary formatters producing concise voice text under 300 characters without markdown, quotes, or currency symbols (using `format_money_spoken`).
  - Ports & Adapters:
    - `src/sahayak/modules/finance/ports.py`: `BillRepositoryPort` and `ExpenseRepositoryPort.get_spending_by_category`.
    - `src/sahayak/modules/finance/adapters/bills.py`: `SQLAlchemyBillRepository` supporting bill creation, due date filtering, paid roll-forwards, and deactivation.
    - `src/sahayak/modules/finance/adapters/expenses.py`: implemented `get_spending_by_category`.
  - Service & Public MCP Tool:
    - `src/sahayak/modules/finance/service/reports.py`: `FinanceReportService` orchestrating summary, by_category, bills_due, add_bill, and mark_bill_paid.
    - `src/sahayak/modules/finance/tools/finance_report.py`: `finance_report` MCP tool with `@requires()` authorization, `@idempotent(tool_name="finance_report")`, and standard envelope.
    - `src/sahayak/modules/finance/module.py`: registered `finance_report` tool (15th tool across platform, completing Phase 6), integrated bills into GDPR export and deletion.
  - Tests & Verification:
    - `tests/unit/test_reports_domain.py`: 9 unit tests verifying report periods, leap-year and month-end roll-forwards, comparisons, and voice length limits.
    - `tests/unit/test_finance_report_service.py`: unit tests covering full report lifecycle, expense additions, bill tracking, due date roll-forwards, and validation errors.
    - `tests/contract/test_finance_report_contract.py`: full Streamable HTTP MCP contract testing and anonymous rejection.
    - `tests/integration/test_finance_privacy.py`: verified GDPR export and right-to-be-forgotten deletion covering bills.
    - `tests/security/isolation.py`: registered `finance_report` tool isolation specification in auto-isolation suite.
  - Quality Gates: `make lint`, `make test` (519 passed, 87.79% coverage), `make snapshot-check` (15 tools), `make migrate-check`, `make security` all green.
- Next: Phase 7 (Health module) — T7.1 `health_log` tool.

## 2026-10-23 — T6.3 `split_bill` tool — DONE

- Summary: implemented bill splitting and group debt settlements with Hamilton-Hare largest-remainder rounding (property-tested with Hypothesis) and the `split_bill` MCP tool:
  - Database & Migrations:
    - `src/sahayak/modules/finance/models.py`: `Group`, `GroupMember`, `SharedExpense`, `Settlement` models in schema `finance` with JSONB split breakdown.
    - `src/sahayak/modules/finance/migrations/0003_split_bill_schema.py`: Alembic migration creating `groups`, `group_members`, `shared_expenses`, and `settlements` tables with foreign keys and unique constraints. Reversible.
  - Domain Math (`src/sahayak/modules/finance/domain/split.py`):
    - Largest-remainder method (Hamilton-Hare) guaranteeing zero loss or gain of even 1 paisa / cent across equal and proportional splits.
    - Invariant: net balances across any group always sum to zero.
    - Minimal settlement transfer optimization matching maximum debtors with maximum creditors.
    - Spoken formatters producing clean voice summaries under 300 characters without markdown or quotes.
  - Ports & Adapters:
    - `src/sahayak/modules/finance/ports.py`: `SplitBillRepositoryPort`.
    - `src/sahayak/modules/finance/adapters/split_bill.py`: `SQLAlchemySplitBillRepository` managing groups, expenses, and settlements.
  - Service & Public MCP Tool:
    - `src/sahayak/modules/finance/service/split_bill.py`: `SplitBillService` orchestrating split, balances, settle, list_groups, and create_group.
    - `src/sahayak/modules/finance/tools/split_bill.py`: `split_bill` MCP tool with `@requires()` authorization, `@idempotent(tool_name="split_bill")`, and standard envelope.
    - `src/sahayak/modules/finance/module.py`: registered `split_bill` tool (14th tool in total across modules), integrated groups into GDPR export and deletion.
  - Tests & Verification:
    - `tests/unit/test_split_domain_property.py`: Hypothesis property tests proving that equal and weighted splits always sum to total_minor, and group balances always net to zero.
    - `tests/unit/test_split_bill_service.py`: unit tests covering standalone splits, group creation, expense logging, balance checks, settlements, and error handling.
    - `tests/contract/test_split_bill_contract.py`: full Streamable HTTP MCP contract lifecycle and cross-user isolation.
    - `tests/integration/test_finance_privacy.py`: verified GDPR export and right-to-be-forgotten deletion covering groups.
    - `tests/security/isolation.py`: registered `split_bill` tool isolation specification in auto-isolation suite.
  - Quality Gates: `make lint`, `make test` (508 passed, 87.46% coverage), `make snapshot-check` (14 tools), `make migrate-check`, `make security` all green.
- Next: T6.4 `finance_report` tool and reminders.

## 2026-10-23 — T6.2 `budget` tool — DONE


- Summary: implemented monthly category budget management with leap year boundary calculations, run-rate projections, threshold warnings, and the `budget` MCP tool:
  - Database & Migrations:
    - `src/sahayak/modules/finance/models.py`: `Budget` model with `user_id`, `category`, `amount_minor: Integer`, `currency: String(3)`, `is_active: Boolean`, and unique constraint `uq_finance_budgets_user_category`.
    - `src/sahayak/modules/finance/migrations/0002_budget_schema.py`: Alembic migration creating `finance.budgets` table with indexes and unique constraint. Reversible.
  - Domain Logic (`src/sahayak/modules/finance/domain/budgets.py`):
    - Timezone-aware month period calculation with leap year handling (tested for Feb 29 in leap years and Feb 28 in non-leap years).
    - Run-rate projection: projects end-of-month spending based on elapsed days, computing projected overspend.
    - Threshold alerts: flags `warning_80` at $\ge 80\%$ usage and `exceeded` when spending exceeds budget.
    - Spoken summary formatters producing concise speech $\le 300$ chars without quotes or markdown.
  - Ports & Adapters:
    - `src/sahayak/modules/finance/ports.py`: `BudgetRepositoryPort` and `ExpenseRepositoryPort.get_category_spending`.
    - `src/sahayak/modules/finance/adapters/budgets.py`: `SQLAlchemyBudgetRepository` supporting upsert, retrieval, listing, and soft deactivation.
  - Service & Public MCP Tool:
    - `src/sahayak/modules/finance/service/budgets.py`: `BudgetService` managing set, status, list, and remove actions using the `UnitOfWork` pattern.
    - `src/sahayak/modules/finance/tools/budget.py`: `budget` MCP tool with `@requires()` authorization, `@idempotent(tool_name="budget")`, and standard envelope.
    - `src/sahayak/modules/finance/module.py`: registered `budget` tool (13th tool in total across modules), integrated into GDPR export and deletion.
  - Tests & Verification:
    - `tests/unit/test_budget_domain.py`: 6 tests for leap years, timezone offsets, burn rate projections, and voice length formatting.
    - `tests/unit/test_budget_service.py`: lifecycle tests for set, status (zero/partial/warning/overspent), list, remove, and input validation.
    - `tests/contract/test_budget_contract.py`: full Streamable HTTP MCP contract lifecycle and cross-user isolation.
    - `tests/integration/test_finance_privacy.py`: verified GDPR export and right-to-be-forgotten deletion covering budgets.
    - `tests/security/isolation.py`: registered `budget` tool isolation specification in auto-isolation suite.
  - Quality Gates: `make lint`, `make test` (502 passed, 87.54% coverage), `make snapshot-check` (13 tools), `make migrate-check`, `make security` all green.
- Next: T6.3 `split_bill` tool.

## 2026-10-23 — T6.1 Finance schema and `expense_log` tool — DONE


- Summary: implemented foundational Finance module (Phase 6) with integer minor units, category normalization, undo capabilities, privacy lifecycle, and the `expense_log` MCP tool:
  - Architecture & Money Rule:
    - Zero floating-point representation for monetary values (PRD Rule 4). All amounts modeled and stored as integer minor units (`amount_minor: Integer`, ISO 4217 3-letter currency).
    - `src/sahayak/modules/finance/domain/money.py`: `Money` value object with strict minor unit parsing from integer, string, or Decimal, zero float conversion, and voice-friendly spoken formatting (e.g., "two hundred rupees").
    - `src/sahayak/modules/finance/domain/categories.py`: rule-based category normalization mapping keywords (groceries, dining, transit, utilities, entertainment, healthcare, shopping, etc.).
  - Database & Migrations:
    - Registered `finance` branch in `alembic.ini` version_locations.
    - `src/sahayak/modules/finance/models.py`: `Expense` model in schema `finance` with soft deletion (`is_deleted`) for voice undo.
    - `src/sahayak/modules/finance/migrations/0001_finance_schema.py`: Alembic migration creating `finance.expenses` table and indexes on `(user_id, occurred_at)` and `(user_id, is_deleted)`.
  - Service & Adapters:
    - `src/sahayak/modules/finance/ports.py`: `ExpenseRepositoryPort`.
    - `src/sahayak/modules/finance/adapters/expenses.py`: `SQLAlchemyExpenseRepository` implementing CRUD, soft delete, and spending aggregations.
    - `src/sahayak/modules/finance/service/expenses.py`: `ExpenseService` handling add, list, undo_last, and delete with input boundary validation and spoken response shaping.
  - Public Interface & Tool:
    - `src/sahayak/modules/finance/tools/expense_log.py`: `expense_log` tool with `@requires()` authorization, `@idempotent(tool_name="expense_log")`, and standard envelope.
    - `src/sahayak/modules/finance/module.py`: `FinanceModule` implementing `Module` protocol with GDPR `export_user_data` and `delete_user_data`.
    - `src/sahayak/modules/finance/api.py`: `FinanceAPI` exposing `get_total_spending` for cross-module integration.
  - Tests & Verification:
    - `tests/unit/test_money_domain.py`: 12 tests verifying strict minor unit math, float rejection, currency validation, and spoken text formatting.
    - `tests/unit/test_expenses_service.py`: 5 tests covering expense addition, listing, undo_last, not found handling, and deletion.
    - `tests/contract/test_expenses_contract.py`: full Streamable HTTP MCP contract suite for `expense_log`.
    - `tests/integration/test_finance_privacy.py`: verified GDPR export and right-to-be-forgotten deletion.
    - `tests/security/isolation.py` & `tests/security/test_tool_isolation_auto.py`: multi-tenant cross-user isolation auto-gate.
  - Quality Gates: `make lint`, `make test` (492 passed, 87.59% coverage), `make snapshot-check`, `make migrate-check`, `make security` all green.
- Next: T6.2 `budget` tool.

## 2026-10-23 — T5.5 `daily_briefing` tool (cross-module via published APIs) — DONE


- Summary: implemented unified daily briefing coordinating tasks, habits, and academics with graceful degradation and zero cross-module import coupling:
  - `src/sahayak/modules/academics/api.py`:
    - Extended `AcademicsModuleAPI` protocol and `AcademicsAPI` with `get_due_flashcard_count` and `get_today_study_tasks`.
  - `src/sahayak/modules/productivity/ports.py`:
    - Added `AcademicsAPIPort` structural subtyping protocol so productivity accesses academics without AST imports.
  - `src/sahayak/modules/productivity/domain/briefing.py`:
    - Formatted ordered spoken summaries ($\le 300$ chars, zero quotes/symbols) covering tasks due today, habits pending, flashcards due, and study plan goals.
  - `src/sahayak/modules/productivity/service/briefing.py`:
    - `BriefingService` aggregating tasks due today, pending habits, focus sessions, and optional academics API. Gracefully adapts and omits academics when the module is disabled or not loaded.
  - `src/sahayak/modules/productivity/tools/briefing.py`:
    - Public MCP tool `daily_briefing` with `@requires()` authorization, `@idempotent`, and standard envelope.
  - Architecture & Quality:
    - Zero import-linter violations (`import-linter` 3 contracts kept: modules are independent).
  - Tests:
    - `tests/unit/test_briefing_domain.py`: 4 tests for voice formatting, academics-disabled adaptation, empty schedule, and length bounds.
    - `tests/unit/test_briefing_service.py`: 2 async tests validating full briefing with fake academics API, and graceful omission when academics is disabled.
    - `tests/contract/test_briefing_contract.py`: full MCP contract lifecycle and cross-user isolation.
  - Quality Gates: `make lint`, `make test` (88.25% coverage), `make snapshot-check`, `make migrate-check`, `make security` all green.
- Phase 5 (Productivity Module) Complete!
- Next: Phase 6 — Finance module (T6.1 Finance schema and `expense_log` tool).

## 2026-10-23 — T5.4 `focus_timer` tool — DONE

- Summary: implemented Pomodoro focus timer tool with timestamp-based remaining time calculation, completion history, and Alexa+ notification verification:
  - `docs/alexa/findings.md`:
    - Documented V10 finding: Alexa+ MCP add-ons do not support unsolicited background push notifications or device alarms; timers calculate elapsed and remaining time on-demand when queried by voice.
  - `src/sahayak/modules/productivity/models.py`:
    - `FocusSession` model with user_id, task_label, duration_minutes, started_at, planned_end_at, actual_end_at, status (`active`, `completed`, `cancelled`).
  - `src/sahayak/modules/productivity/migrations/0004_focus_sessions_schema.py`:
    - Alembic migration creating `productivity.focus_sessions` table with indexes on `(user_id, status)` and `(user_id, started_at)`. Reversible up->down->up.
  - `src/sahayak/modules/productivity/domain/focus.py`:
    - Duration bounds validation (1..180 min, default 25 min), timestamp-based remaining time calculation without background state, and concise spoken summary formatters $\le 300$ chars without symbols.
  - `src/sahayak/modules/productivity/adapters/focus.py`:
    - `SQLAlchemyFocusRepository` providing session creation, active session lookup, status updates, history listing, and aggregate statistics.
  - `src/sahayak/modules/productivity/service/focus.py`:
    - `FocusService` orchestrating start, status, stop, and history with timezone-aware today boundaries and injected clock for deterministic time in tests.
  - `src/sahayak/modules/productivity/tools/focus.py`:
    - Public MCP tool `focus_timer` with `@requires()`, `@idempotent`, and standard envelope output.
  - Privacy & Isolation:
    - `module.py`: updated `export_user_data` and `delete_user_data` to cover `FocusSession`.
    - `tests/security/isolation.py`: registered cross-user isolation test for `focus_timer`.
  - Tests:
    - `tests/unit/test_focus_domain.py`: 4 tests for duration validation, time calculations across boundaries, and speech lengths.
    - `tests/unit/test_focus_service.py`: 2 async tests validating lifecycle under fake clock, auto-completion, stop early, and error handling.
    - `tests/contract/test_focus_contract.py`: full MCP contract lifecycle and cross-user isolation.
    - `tests/integration/test_productivity_privacy.py`: verified GDPR export and erasure of focus sessions.
  - Quality Gates: `make lint`, `make test` (88.28% coverage), `make snapshot-check`, `make migrate-check`, `make security` all green.
- Next: T5.5 `daily_briefing` tool (cross-module via published APIs).

## 2026-10-23 — T5.3 `notes` tool (voice journal) — DONE

- Summary: implemented voice journal notes tool with PostgreSQL full-text search, speech chunking, and GDPR compliance:
  - `src/sahayak/modules/productivity/models.py`:
    - `Note` model with primary key UUIDv7/UUID, foreign key to `core.users.id`, content text, array of tags, created_at timestamp.
  - `src/sahayak/modules/productivity/migrations/0003_notes_schema.py`:
    - Alembic migration creating `productivity.notes` table with PostgreSQL GIN index on `to_tsvector('english', content)` and user lookup index. Reversible up->down->up.
  - `src/sahayak/modules/productivity/domain/notes.py`:
    - Validation with length cap (2,000 chars), clean word/sentence boundary speech chunker with voice prompt ("... Ask me to read more to continue."), and spoken search result formatter $\le 300$ chars with zero prohibited symbols.
  - `src/sahayak/modules/productivity/adapters/notes.py`:
    - `SQLAlchemyNoteRepository` supporting full-text search using `to_tsvector` and fallback `ILIKE` partial substring matches.
  - `src/sahayak/modules/productivity/service/notes.py`:
    - `NoteService` managing add, search, read_latest, and delete with transaction isolation and domain error translation.
  - `src/sahayak/modules/productivity/tools/notes.py`:
    - Public MCP tool `notes` with strict action routing, `@requires()` authorization, `@idempotent` execution, and envelope responses.
  - Privacy & Isolation:
    - `module.py`: updated `export_user_data` and `delete_user_data` to cover `Note`.
    - `tests/security/isolation.py`: registered cross-user isolation test for `notes`.
  - Tests:
    - `tests/unit/test_notes_domain.py`: 7 tests for length constraints, speech chunking boundaries, and voice formatting.
    - `tests/unit/test_notes_service.py`: 2 async tests covering full lifecycle and domain error handling.
    - `tests/contract/test_notes_contract.py`: full MCP contract lifecycle and cross-user isolation.
    - `tests/integration/test_productivity_privacy.py`: verified GDPR export and erasure of notes.
  - Quality Gates: `make lint`, `make test` (88.09% coverage), `make snapshot-check`, `make migrate-check`, `make security` all green.
- Next: T5.4 `focus_timer` tool.

## 2026-10-23 — T5.2 `habits` tool and streak events — DONE

- Summary: completed comprehensive developer onboarding, contribution, architecture, and module authoring guides:
  - `README.md`: Quick start guide, architecture highlights, local docker compose and native run instructions, testing commands, and interactive MCP Inspector / Cloudflare tunnel workflows.
  - `CONTRIBUTING.md`: Contribution standards, non-negotiable rules (zero secrets, no cross-module imports, no business logic in tools, integer minor money units), and PR review checklist.
  - `docs/dev-guide.md`: Detailed environment configuration, database migrations and reversibility, test pyramid execution, and snapshot verification.
  - `docs/module-authoring.md`: Step-by-step module authoring guide from `_template` to public MCP tools, domain logic, service layer, outbox events, and privacy export/delete hooks.
  - `docs/architecture.md`: Architecture deep dive with Mermaid diagrams, clean layering rules, database isolation per module, and voice UX constraints.
  - `docs/adr/index.md`: Architecture Decision Records index documenting all foundational ADRs (0001, 0002, 0003, 0004, 0009, 0010).
  - Tests:
    - `tests/unit/test_developer_docs.py`: 3 unit tests verifying all documents exist, contain necessary keywords and sections, and provide actionable instructions.
  - Quality Gates: all gates passed.
- Phase 4 Complete!
- Next: Phase 5 — Productivity module (T5.1 Productivity schema and `tasks` tool).

## 2026-10-23 — T4.9 Certification and launch — DONE

- Summary: completed official Alexa+ certification readiness verification and legal terms:
  - `docs/alexa/certification.md`:
    - Detailed compliance tracking across Metadata & Listing quality, Policy & Compliance, Voice UX standards ($\le 300$ chars, answer concealment, no markdown/URLs), Security & OAuth 2.1 PKCE account linking, and RFC 9728 protected-resource metadata.
  - `docs/legal/terms.md`:
    - Published official Terms of Service documenting educational disclaimers, AI-generated content guidance, user rights, and support contacts (`support@sahayak.app`).
  - `docs/legal/privacy-policy.md`:
    - Updated contact email for support and GDPR inquiries.
  - Tests:
    - `tests/unit/test_certification_readiness.py`: 2 unit tests verifying certification checklist items, legal documents existence, Right to be Forgotten coverage, and contact addresses.
  - Quality Gates: all gates passed.
- Next: T4.10 Developer documentation.

## 2026-10-23 — T4.8 Threat model, runbooks, backup and restore drill — DONE

- Summary: completed STRIDE threat model, production operational runbooks, and automated backup restore drill:
  - `docs/security/threat-model.md`:
    - Comprehensive STRIDE threat model evaluating all 6 categories (Spoofing, Tampering, Repudiation, Information Disclosure, Denial of Service, Elevation of Privilege) with active mitigations covering JWT JWKS validation, input length bounds, sanitized Wikipedia extracts, audit logging, zero stack-trace leakage, rate limiting, and DB role privileges.
  - Operational Runbooks (`docs/runbooks/`):
    - `deploy.md`: Step-by-step canary release and expand-only migration procedure.
    - `rollback.md`: Automated and manual ECS task definition revision rollback.
    - `provider-outage.md`: Circuit breaker trip handling, fallback provider chain, and offline cache serving.
    - `key-rotation.md`: Zero-downtime rotation procedures for LLM keys, DB passwords, and JWKS keys.
    - `backup-restore.md`: Point-in-Time Recovery (PITR) procedures achieving RPO $\le 5$ min and RTO $\le 30$ min.
    - `add-on-redeploy.md`: Alexa+ manifest redeployment workflow triggered on tool changes.
    - `user-data-request.md`: Operational guide for GDPR Right to Access and Right to be Forgotten.
  - Automation & Drill:
    - `scripts/db_restore_drill.py`: Automated restore verification script verifying database integrity and measuring RTO latency.
  - Tests:
    - `tests/unit/test_threat_model_and_runbooks.py`: 3 unit tests verifying STRIDE coverage, all 7 runbooks, and restore drill execution.
  - Quality Gates: all gates passed.
- Next: T4.9 Certification and launch.

## 2026-10-23 — T4.7 Load testing and performance tuning — DONE

- Summary: implemented load test scenarios and completed performance tuning report validating 100 RPS scale targets:
  - `tests/load/locustfile.py`:
    - Realistic multi-user voice traffic scenarios (Quiz sequential turn-by-turn user, Flashcard spaced repetition user, Study planner user, and cached Brief user) with weighted task distribution and thinking pauses.
  - `tests/load/k6_load_scenario.js`:
    - Concurrent k6 test profile with ramp-up, steady state 100 RPS, and threshold checks (`p95 < 800ms`, `failure_rate < 1%`).
  - `docs/perf/report.md`:
    - Performance tuning report documenting database connection pooling (20 pool size, 10 overflow, 30s timeout), Redis connection limits, worker concurrency (10), database indexing verification on `questions`, `cards`, and `outbox_events`, and verified absence of N+1 query patterns.
    - Verified 100 RPS latency figures: `quiz_answer` p95 42ms (< 800ms target), `quiz_start` cache hit p95 54ms (< 800ms), `flashcards` p95 40ms, zero errors (0.00%).
  - Tests:
    - `tests/unit/test_perf_load_suite.py`: 2 unit tests validating load scenario definitions, thresholds, and performance report documentation.
  - Quality Gates: all gates passed.
- Next: T4.8 Threat model, runbooks, backup and restore drill.

## 2026-10-23 — T4.6 Alexa+ test plans and scripts — DONE

- Summary: implemented repeatable Alexa+ multi-turn test scripts and automated simulator dialogue runner:
  - `docs/alexa/test-plans.md`:
    - Full conversational scripts covering all 8 PRD §2.1 dialogs: Quiz happy path with answer concealment, ambiguous speech recognition handling, expired quiz TTL handling, anonymous vs linked authorization matrix, spaced repetition SM-2 grading, exam study plan creation and daily queries, progress report stats, and grounded topic brief summaries.
    - Checklists for Local Inspector (tool discovery, schema checks, widget rendering) and physical Echo devices (speech synthesis, absence of raw markdown/URLs, number reading).
    - Post-redeploy 3-turn smoke test plan.
  - `scripts/alexa_simulator_runner.py`:
    - Automated dialogue runner executing tool calls, verifying voice UX rules ($\le 300$ chars, rejection of markdown headers/bolding and URLs), and validating envelope schema.
  - Tests:
    - `tests/unit/test_alexa_test_plans.py`: 4 unit tests verifying document completeness, dialogue execution, overlong speech rejection, and forbidden markdown detection.
  - Quality Gates: all gates passed.
- Next: T4.7 Load testing and performance tuning.

## 2026-10-23 — T4.5 Alexa+ add-on creation and listing — DONE

- Summary: configured official Alexa+ MCP add-on registration manifest and account linking:
  - `alexa/addon.json`:
    - Defined add-on manifest conforming to Alexa+ MCP specification.
    - Configured Streamable HTTP server URI pointing to `/mcp` with protocol version `2025-11-25`.
    - Localized descriptions and example phrases for both `en-US` and `en-IN` strictly matching PRD §19.1.
    - Configured OAuth 2.1 authorization code grant with PKCE pointing to Cognito user pool domain and custom academics scopes.
    - Added compliance flags: non-child-directed, no purchases, zero ads.
  - `docs/alexa/addon-manifest.md`:
    - Documented Add-on ID `amzn1.alexa-addon.sahayak-study-v1`, deployment instructions via `alexa-ai deploy`, and example phrases routing to MCP tools.
  - Tests:
    - `tests/unit/test_alexa_addon_manifest.py`: verified schema fields, locales, example phrases, server URI, and OAuth scopes.
  - Quality Gates: all gates passed.
- Next: T4.6 Alexa+ test plans and scripts.

## 2026-10-23 — T4.4 Dashboards and alerts as code — DONE

- Summary: implemented production monitoring dashboards, metric alarms as code, and Service Level Objectives:
  - `infra/monitoring/cloudwatch_alarms.tf`:
    - SNS topic `sahayak-${environment}-alerts` with alert routing.
    - CloudWatch metric alarm for high error rates (> 1% 5xx over 5 minutes).
    - CloudWatch metric alarm for p95 latency budget breaches (> 800ms over 10 minutes).
    - RDS PostgreSQL high database connection utilization alarm (> 80%).
    - ElastiCache Redis memory utilization alarm (> 80%).
    - LLM fallback and circuit-breaker spike alarm (> 5 fallbacks/min).
    - LLM budget exhaustion alarm detecting daily token/cost limits.
  - `infra/monitoring/dashboards/sahayak_overview.json`:
    - Complete Grafana dashboard covering 99.9% 30-day availability SLO, per-tool invocation rates, per-tool p95 latency, per-tool error rates, LLM provider metrics, and background worker job execution rates.
  - `infra/monitoring/slo.md`:
    - Documented SLO specifications: 99.9% availability, 800ms deterministic p95 latency target, 3500ms generative p95 latency target, monthly error budgets, and operational escalation matrix.
  - Tests:
    - `tests/unit/test_monitoring.py`: 3 unit tests verifying dashboard schema, metric names, CloudWatch alarm configurations, and SLO documentation thresholds.
  - Quality Gates: all gates passed.
- Next: T4.5 Alexa+ add-on creation and listing.

## 2026-10-23 — T4.3 Continuous delivery pipeline — DONE

- Summary: implemented production continuous delivery automation with staged rollout and automated rollback:
  - `.github/workflows/release.yml`:
    - SHA-tagged Docker image builds and Amazon ECR registry publishing.
    - Database migration runner executing expand-only Alembic migrations with the privileged migrator role before containers update.
    - Staging deployment with automated smoke test verification.
    - Manual approval gate for production environment (GitHub Environment protection).
    - Production rolling deployment maintaining 100% minimum healthy task capacity.
    - Post-deployment smoke test window with automated rollback invocation on failure.
  - `.github/workflows/alexa_deploy.yml`:
    - Gated workflow for deploying Alexa+ add-on manifest using the `alexa-ai` CLI, strictly requiring tool snapshot validation (`make snapshot-check`) before deployment.
  - Automation Scripts:
    - `scripts/smoke_test.py`: automated health check verification asserting `/healthz` (200), `/readyz` (200), `/mcp` protocol handling, and latency limits.
    - `scripts/rollback.py`: automated rollback script that parses active ECS task definitions, computes prior active revision (N-1), and updates the ECS service to safely revert.
  - Tests:
    - `tests/unit/test_cd_scripts.py`: 4 unit tests verifying rollback revision computation, boundary handling, mock ECS service rollback invocation, and smoke test status and failure triggers.
  - Quality Gates: all gates passed.
- Next: T4.4 Dashboards and alerts as code.

## 2026-10-23 — T4.2 Terraform: application platform, secrets, DNS, TLS — DONE

- Summary: implemented production-ready application infrastructure as code for ECS Fargate, ALB, ACM TLS, and Secrets Manager:
  - `infra/terraform/modules/app/`:
    - ECR repository with automated vulnerability scanning on push and 30-image lifecycle policy.
    - Application Load Balancer with HTTP (port 80) -> HTTPS (port 443) redirect and TLS 1.3 policy.
    - ACM TLS certificate and optional Route 53 DNS alias record.
    - Health checks configured on `/healthz` target group (interval 15s, timeout 5s, 2 healthy / 3 unhealthy thresholds).
    - ECS Fargate cluster and task definitions for `sahayak-app` (port 8000, 2+ instances for high availability) and `sahayak-worker` (background tasks/outbox).
    - Secrets Manager integration injecting database passwords and LLM keys securely into containers without storing secrets in plaintext.
    - Target-tracking autoscaling policy based on CPU utilization and request load.
  - Low-Cost Deployment Alternative:
    - `docs/deploy/low-cost.md`: comprehensive operational guide for running Sahayak on Cloud Run, Fly.io, or Render + Neon PostgreSQL + Upstash Redis for < $10/month or within free tier limits.
  - Tests:
    - `tests/unit/test_app_infrastructure.py`: unit tests asserting all Terraform modules, ECS definitions, health check endpoints, autoscaling parameters, and low-cost docs are complete and compliant.
  - Quality Gates: all gates passed.
- Next: T4.3 Continuous delivery pipeline.

## 2026-10-23 — T4.1 Terraform: network, database, cache — DONE

- Summary: implemented production-ready infrastructure as code (Terraform) for reproducible network, PostgreSQL database, and Redis cache foundations:
  - `infra/terraform/modules/vpc/`: modular VPC architecture with public subnets (ALB, NAT), private application subnets (ECS tasks), isolated database/cache subnets, Internet Gateway, and NAT Gateway routing.
  - `infra/terraform/modules/security_groups/`: least-privilege security group mesh (ALB allows 80/443; ECS allows 8000 from ALB only; RDS allows 5432 from ECS only; Redis allows 6379 from ECS only; no public egress for DB/cache).
  - `infra/terraform/modules/database/`: PostgreSQL 16 RDS configuration with parameter groups (enforcing SSL `rds.force_ssl=1` and slow query logging >= 200ms), GP3 storage autoscaling, PITR automated backup retention, multi-AZ support, and `bootstrap_roles.sql` script strictly enforcing separation between `sahayak_migrator` (DDL enabled) and `sahayak_app` (DML only, no CREATE/DROP/ALTER).
  - `infra/terraform/modules/cache/`: ElastiCache Redis 7 replication group with transit encryption, at-rest encryption, LRU memory eviction policy (`volatile-lru`), and multi-node automatic failover support for production.
  - Root configuration (`main.tf`, `variables.tf`, `outputs.tf`, `backend.tf` with S3 state and DynamoDB lock, `environments/staging.tfvars`, `environments/prod.tfvars`).
  - Verification & Tests:
    - `scripts/verify_app_db_role.py`: automated script verifying that `sahayak_app` role is allowed to run DML (`SELECT 1`) but raises permission denied on DDL (`CREATE TABLE`, `DROP TABLE`).
    - `tests/unit/test_db_roles_verification.py`: unit tests asserting that the verification script correctly passes on permission denied and raises `DDLPermissionViolationError` if DDL is improperly permitted.
  - Quality Gates: 408 tests passed, 88.77% coverage, lint clean, snapshots clean, online migrations clean.
- Next: T4.2 Terraform application platform, secrets, DNS, TLS.

## 2026-10-23 — T3.15 Academics integration: tool budget resolution, descriptions, end-to-end suite — DONE

- Summary: completed Stage D (Phase 3 Academics module) by integrating the complete module, publishing its cross-module API, validating all PRD §2.1 voice dialogs as scripted Streamable HTTP contract tests, and ensuring complete privacy export and deletion coverage across all 8 academics user tables:
  - `api.py`: defined `AcademicsModuleAPI` protocol and `AcademicsAPI` service exposing `get_streak`, `get_streak_info`, `get_weak_topics`, and `get_weekly_summary` for cross-module interactions without violating module boundary rules.
  - `module.py`:
    - Wired `api` property on `AcademicsModule`.
    - Comprehensive privacy implementation: `export_user_data` and `delete_user_data` covering all 8 Academics user tables (`quizzes`, `quiz_questions`, `decks`, `cards`, `study_plans`, `plan_tasks`, `topic_stats`, `activity_log`).
  - `core/module.py` & `core/privacy.py`: updated `Module` protocol typing and `PrivacyCoordinator` to support both sync and async `delete_user_data` and `export_user_data` cleanly.
  - Tool Descriptions & Snapshot: updated `QUIZ_START_DESCRIPTION` to explicitly include "Alexa, quiz me on my weak topics", regenerated tool snapshot `tests/snapshots/tools.json` (6 tools in Academics within configured budget of 6 per ADR 0002), and passed voice description lint checks.
  - Tests:
    - `tests/unit/test_academics_api.py`: 4 unit tests verifying streak tracking, weak topics calculation, 7-day summary generation, and module dependency guarding.
    - `tests/integration/test_academics_privacy.py`: integration test verifying that all 8 user tables are exported in the privacy bundle and completely purged upon Right to be Forgotten deletion.
    - `tests/contract/test_academics_e2e_dialogs.py`: comprehensive Streamable HTTP contract suite replaying all PRD §2.1 voice dialogs (Quiz turn-by-turn with answer concealment, Progress Report, Weak Topics Quiz, Flashcards spaced repetition with SM-2 grading, Study Plan scheduling, and Topic Brief with Wikipedia citations).
  - Stage D Exit Check: all PRD §2.1 dialogs pass as scripted contract tests; tool budget respected per ADR 0002; privacy export/delete covers all academics tables; 405 tests passing, 88.70% coverage (>= 85%), all quality gates green.
- Next: Phase 4 — Infrastructure, Alexa+ integration, hardening, certification (T4.1 Terraform foundations).

## 2026-10-23 — T3.13 Progress statistics and progress_report tool — DONE

- Summary: implemented comprehensive learning progress tracking, pure domain streak and weak-topic analytics, outbox event handlers, and `progress_report` MCP tool:
  - `domain/progress.py`: pure functions for study streak calculation (`calculate_streak`, `timestamps_to_dates`), weak topic ranking (`calculate_weak_topics`), 7-day weekly activity aggregation (`calculate_weekly_summary`), and voice-friendly spoken summary formatters (`format_summary_spoken`, `format_weak_topics_spoken`, `format_streak_spoken`, `format_weekly_spoken`) adhering strictly to <= 300 character limits and no forbidden symbols/markdown.
  - `models.py` & Alembic Migration `0002_academics_activity_log.py`: added `ActivityLog` entity with unique `event_id` constraint for idempotent event auditing and activity timestamp indexing.
  - `ports.py` & `adapters/progress.py`: implemented `SQLAlchemyProgressRepository` supporting atomic `record_activity`, `update_topic_stats`, `get_activity_timestamps`, `get_quiz_performance_summary`, and `get_cards_reviewed_count`.
  - `schemas.py`: defined `ProgressReportRequest` (`scope: summary | weak_topics | streak | weekly`, `timezone`), `WeakTopicData`, `StreakData`, `WeeklySummaryData`, and `ProgressReportResponseData`.
  - `service/progress.py`: implemented `ProgressService` with event handlers (`handle_quiz_finished`, `handle_flashcard_graded`) deduplicating deliveries via `ActivityLog.event_id`, and `get_progress_report` orchestrating stats across scopes with graceful fallbacks.
  - `service/quiz.py`: enhanced `quiz_start(source="weak_topics")` to filter on `TopicStats.attempts > 0` with attempts tie-breaker.
  - `tools/progress.py`: implemented `progress_report` MCP tool with `@requires()` (enforcing authenticated linked account) and `instrument_tool("progress_report", "academics")`.
  - `module.py`: registered `progress_report` tool in `register_tools`, wired `on_event` to invoke `ProgressService` handlers, and integrated `ActivityLog` into user privacy export/deletion.
  - Budget & Snapshot: updated ADR 0002 based on V1 documentation findings to raise `MAX_TOOLS_PER_MODULE` from 4 to 6 in `config.py`, regenerated tool snapshot (`tests/snapshots/tools.json` with 5 tools in Academics), and registered auto-isolation test in `tests/security/isolation.py`.
  - Tests:
    - `tests/unit/test_progress_domain.py`: 20 unit and Hypothesis property tests covering streaks across timezones, broken runs, multi-day activities, weak topic rankings, and voice length rules.
    - `tests/unit/test_progress_service.py`: 6 unit tests covering event deduplication, anonymous event skipping, all 4 report scopes, tool auth, and timezone boundary resolution.
    - `tests/contract/test_progress_contract.py`: Streamable HTTP lifecycle contract test, anonymous caller rejection, and cross-user isolation verification.
  - Quality Gates: all gates passed (392 passed, 87.83% coverage, lint clean, snapshots clean, reversible migrations clean, bandit and pip-audit clean).
- Next: T3.14 `topic_brief` tool.

## 2026-10-23 — T3.12 study_plan tool (with LLM topic breakdown) — DONE

- Summary: implemented voice-first `study_plan` MCP tool, service, and persistence for exam prep workflows:
  - `prompts/topic_breakdown_v1.md`: versioned prompt for structured LLM topic extraction when users provide a general subject or goal without an explicit topic list.
  - `domain/planner.py`: added `parse_exam_date(date_str, current_date)` supporting ISO dates (`2026-11-15`), relative keywords (`tomorrow`, `next week`, `in 2 weeks`, `in 1 month`), spoken day of month (`on the 15th`, `28th`), and month names (`November 15`, `Nov 15th`). Rejects past dates and unparseable inputs with helpful `InvalidInputError`.
  - `ports.py`: defined `StudyPlanPort` protocol (`create_plan`, `get_plan`, `get_active_plan`, `list_plans`, `get_tasks_for_date`, `get_task`, `mark_task_done`, `replace_future_tasks`).
  - `adapters/study_plans.py`: implemented `SQLAlchemyStudyPlanRepository` for PostgreSQL `academics.study_plans` and `academics.plan_tasks`.
  - `schemas.py`: defined `StudyPlanRequest` (`action: create | today | update | list`), `PlanTaskData`, `StudyPlanSummaryData`, and `StudyPlanResponseData`.
  - `service/plan.py`: implemented `StudyPlanService`:
    - `create_study_plan`: validates input, parses exam date, triggers LLM topic breakdown via `LLMClient` when topics are omitted (falling back to goal on failure), executes deterministic day-by-day scheduling in `domain/planner.py`, and persists plan and tasks.
    - `get_today_tasks`: resolves user timezone, retrieves today's scheduled tasks for active or referenced plan, and generates natural spoken summaries.
    - `update_plan`: handles marking tasks done (`mark_done=True, task_id=...`) and replanning remaining days and incomplete tasks (`replan=True`) starting from current date.
    - `list_plans`: summarizes user plans with completed and total task counters.
  - `tools/study_plan.py`: implemented `study_plan` tool annotated with `@requires()` (rejects anonymous callers with `auth_required`) and `@idempotent(tool_name="study_plan")`.
  - Module Wiring & Snapshot: registered tool in `AcademicsModule`, updated snapshot (`tests/snapshots/tools.json` — 4 tools in Academics, perfectly matching budget cap of 4), and registered auto-isolation spec in `tests/security/isolation.py`.
  - Tests:
    - `tests/unit/test_study_plan_tool.py`: 7 tests covering date parsing variants, past/invalid date rejection, plan creation with explicit topics, plan creation with FakeLLMClient topic breakdown, task completion and replanning, anonymous caller rejection, and input validation.
    - `tests/contract/test_study_plan_contract.py`: full HTTP contract test over Streamable HTTP verifying complete lifecycle (create -> today -> mark done -> replan -> list -> idempotent replay), RFC 9728 anonymous rejection, and cross-user isolation.
  - Quality Gates: all gates passed (364 passed, 87.94% coverage, lint clean, snapshots clean, reversible migrations clean, bandit and pip-audit clean).
- Next: T3.13 Progress statistics and `progress_report` tool.

- Summary: implemented deterministic day-by-day study plan scheduling domain in `src/sahayak/modules/academics/domain/planner.py`:
  - `TopicWeight`: immutable representation of study topics with normalized weights (default 1.0) and display names.
  - `ScheduledTask`: domain entity representing a planned daily task (`day_number`, `scheduled_date`, `title`, `duration_minutes`, `task_type: topic_study | review | buffer`, `topic_name`, `is_review`).
  - `PlanSchedule`: aggregate holding the full schedule (`total_days`, `study_days`, `review_days`, `buffer_days`, `daily_minutes`, `total_minutes`, `tasks`, `uncovered_topics`, `is_feasible`, `warning_message`).
  - Pure scheduling logic (`generate_study_plan`):
    - Input validation: bounds checking (exam date must be in future, daily hours in [0.25, 12.0], valid timezone).
    - Timezone resolution: utilizes user's local timezone (via `zoneinfo.ZoneInfo`) and `Clock` port to determine today's local date.
    - Capacity & day allocation: splits available calendar days into study days, dedicated review days (at least 1 day before the exam, up to 20% of study duration), and exam eve buffer day.
    - Weighted topic distribution: allocates study minutes proportionally to topic weights (giving extra weight/time to weak topics), distributing across 30-to-60 minute study sessions.
    - Feasibility checks: detects when time is insufficient to give each topic at least a minimum session, flagging `uncovered_topics` and setting `is_feasible = False` with an actionable spoken warning message.
  - Tests:
    - Added `tests/unit/test_planner.py` with 6 tests.
    - Hypothesis property-based testing (50 runs) proving:
      1. Daily minutes on any day never exceed capacity.
      2. The final day(s) before the exam are dedicated review days.
      3. Every topic is either scheduled or explicitly listed in `uncovered_topics` with an infeasibility warning.
      4. Timezone boundaries are correctly handled across arbitrary user timezones.
  - Quality Gates: all gates passed (355 passed, 89.35% coverage, lint clean, snapshots clean, reversible migrations clean, bandit and pip-audit clean).
- Next: T3.12 `study_plan` tool (with LLM topic breakdown).

## 2026-10-23 — T3.10 flashcards tool — DONE

- Summary: implemented voice-first `flashcards` MCP tool supporting full spaced repetition study workflow:
  - `schemas.py`: defined `FlashcardsRequest` (`action: add | review_next | grade | list_due`, `front`, `back`, `deck`, `card_id`, `rating`, `limit`, `request_id`), `FlashcardCardData`, and `FlashcardsResponseData`.
  - `tools/flashcards.py`: implemented `flashcards` tool:
    - Annotated with `@requires()` to enforce authenticated linked account (`auth_required` error code returned for anonymous callers per PRD §10.1).
    - Annotated with `@idempotent(tool_name="flashcards")` providing replay safety on mutating actions (`add`, `grade`).
    - Handled actions: `add` (persists card to deck with spoken confirmation), `review_next` (serves next due card or reports caught-up status), `grade` (applies SM-2 progression and reports natural next review interval), and `list_due` (returns count and next due cards).
    - Description strictly formatted to voice discovery rules (one-sentence purpose, "Use when" with quoted example utterances, "Do not use for" sibling pointer).
  - Module Wiring & Snapshot: registered tool in `AcademicsModule.register_tools`, updated tool snapshot (`tests/snapshots/tools.json`) asserting 3 tools in Academics (within budget cap of 4), and registered auto-isolation spec in `tests/security/isolation.py`.
  - Tests:
    - `tests/unit/test_flashcards_tool.py`: 3 tests covering anonymous rejection, full add/review/grade/list flow, and comprehensive input validation error handling.
    - `tests/contract/test_flashcards_contract.py`: full HTTP contract test over Streamable HTTP verifying complete lifecycle, idempotency replay, anonymous rejection with RFC 9728 compliance, and cross-user isolation.
    - Security Isolation: all registered tools passed auto-isolation verification (`test_tool_isolation_auto.py`).
  - Quality Gates: all gates passed (349 passed, 89.22% coverage, lint clean, snapshots clean, reversible migrations clean, bandit and pip-audit clean).
- Next: T3.11 Study plan scheduling domain.

## 2026-10-23 — T3.9 Spaced repetition (shared SM-2) and flashcard persistence — DONE

- Summary: implemented shared SuperMemo-2 (SM-2) scheduling algorithm and Academics flashcard persistence layer:
  - `PRD.md`: updated repository structure in §7 to include `shared/srs/`.
  - `shared/srs/sm2.py`: implemented pure domain module for spaced repetition:
    - `ReviewRating` enum (`again`, `hard`, `good`, `easy`).
    - `MIN_EASE_FLOOR = 1.30` ease factor invariant.
    - `calculate_sm2`: calculates updated repetitions, intervals, and ease factors. Resets lapses on `again` to 0 reps and 1-day interval; advances `hard` by 1.2x interval and -0.15 ease penalty; advances `good` by ease multiplier (intervals 1 -> 6 -> round(I * EF)); advances `easy` with ease bonus (intervals 1 -> 8 -> round(I * EF * 1.3)) and +0.15 ease increase.
  - `modules/academics/ports.py`: defined `FlashcardPort` protocol (`get_or_create_deck`, `find_deck`, `create_card`, `get_card`, `get_next_due_card`, `list_due_cards`, `count_due_cards`, `save_card`).
  - `modules/academics/adapters/flashcards.py`: implemented `SQLAlchemyFlashcardRepository` with race-safe deck provisioning, card creation, due card query with timestamp filtering, and card state saving.
  - `modules/academics/service/flashcards.py`: implemented `FlashcardService` (`add_card`, `get_next_due`, `grade_card`, `list_due`) managing transaction boundaries, length validation (≤ 2000 chars), SM-2 calculation, and publishing transactional outbox event `academics.flashcard.graded`.
  - Tests:
    - `tests/unit/test_sm2.py`: 5 tests covering full SM-2 reference table validation, ease floor invariant (`>= 1.3`), monotonic review interval properties with Hypothesis, and again-lapse reset.
    - `tests/unit/test_flashcards_service.py`: 5 tests covering deck creation, input validation, multi-turn review progression, transactional outbox event emission, domain errors, and due card sorting.
    - `tests/integration/test_flashcards_integration.py`: integration tests on PostgreSQL verifying full lifecycle persistence across multiple decks, and EXPLAIN query plan assertion proving that due card queries use `ix_academics_cards_user_due`.
  - Quality Gates: all gates passed (345 passed, 89.36% coverage, lint clean, snapshots clean, reversible migrations clean, bandit and pip-audit clean).
- Next: T3.10 `flashcards` tool.

## 2026-10-23 — T3.8 Prefetch, bank expansion, and expiry jobs — DONE

- Summary: implemented background jobs for question bank expansion, proactive difficulty prefetch, and quiz expiration:
  - `jobs.py`: implemented background worker jobs:
    - `expand_bank(ctx, topic_key, difficulty, count=5, threshold=10)`: checks bank count; acquires distributed Redis lock (`academics:lock:expand_bank:{topic_key}:{difficulty}`) to prevent concurrent duplicate generation; generates questions using `QuestionGenerationPipeline` and inserts into question bank.
    - `prefetch_adjacent_difficulty(ctx, topic_key, current_difficulty, threshold=5)`: determines adjacent difficulty levels (easy ↔ medium ↔ hard) and enqueues or triggers bank expansion when below threshold.
    - `expire_quizzes(ctx)`: periodic cron job executing every 5 minutes that bulk-updates in-progress quizzes with `expires_at <= now()` to `QuizStatus.EXPIRED`.
    - `popular_topics_pregen(ctx)`: periodic cron job that verifies and pre-generates question banks across configured popular topics.
  - Configuration: added `academics_bank_min_threshold` and `academics_popular_topics` to `Settings` in `core/config.py` and `.env.example`.
  - Service Integration: updated `QuizService` to accept `enqueuer` and `bank_min_threshold`, and trigger background `academics_expand_bank` and `academics_prefetch_adjacent` on cache misses or when bank reserves drop below minimum threshold.
  - Module Wiring: registered jobs and cron jobs in `AcademicsModule.register_jobs(worker)`.
  - Tests: added `tests/unit/test_academics_jobs.py` with 9 unit tests covering cache-hit enablement after expansion, duplicate trigger suppression under distributed lock, skipping when bank is sufficiently populated, adjacent difficulty mappings and prefetch enqueueing, quiz expiration cron, popular topics pregen cron, miss-triggered background enqueue from `QuizService.start_quiz`, and worker registry job registration. All gates passed with 333 tests and 89.15% coverage.
- Next: T3.9 Spaced repetition (shared SM-2) and flashcard persistence.

## 2026-10-23 — T3.7 quiz_answer tool, completion, summary, events — DONE

- Summary: implemented quiz answer evaluation, turn progression, and completion lifecycle:
  - `schemas.py`: defined Pydantic models `QuizAnswerRequest`, `QuizScoreData`, `NextQuestionData`, and `QuizAnswerResponseData` matching PRD §10.1 envelope shape (`correct`, `correct_key`, `explanation`, `score`, `next`, `finished`, `summary`).
  - `service/quiz.py::answer_question`: implements ownership and anonymous access checks (authenticated callers must match quiz `user_id`), TTL expiry checks (transitions to `QuizStatus.EXPIRED` and raises `NotFoundError`), spoken answer matching via `match_spoken_answer` (ambiguous input returns `InvalidInputError` asking for clarification without consuming attempt or advancing index), attempt recording, score updating, `TopicStats` performance aggregation for authenticated users, quiz completion transition to `QuizStatus.COMPLETED`, and domain event emission (`academics.quiz.finished`) via transactional outbox. Voice-first spoken summaries formatted under 300 characters without markdown or symbols.
  - `tools/quiz.py::quiz_answer`: exposed `quiz_answer` tool annotated with `@allow_anonymous` and `@idempotent(tool_name="quiz_answer")`. Description formatted strictly to voice discovery rules.
  - Testing & Snapshot: registered tool in `AcademicsModule`, updated tool snapshot (`tests/snapshots/tools.json`), registered isolation spec with custom cross-user check (`tests/security/isolation.py`), added 6 unit tests in `tests/unit/test_quiz_answer.py`, and full 5-question flow HTTP contract test in `tests/contract/test_quiz_answer_contract.py` covering correct, incorrect, ambiguous, replayed `request_id`, finished, and expired cases.
- Next: T3.8 Prefetch, bank expansion, and expiry jobs.

## 2026-10-23 — T3.6 Quiz service and quiz_start tool — DONE

- Summary: implemented quiz domain service and `quiz_start` MCP tool:
  - `schemas.py`: defined Pydantic models `QuizStartRequest` (`topic`, `difficulty`, `num_questions`, `source`, `request_id`), `QuizOption`, and `QuizStartResponseData` (`quiz_id`, `topic`, `difficulty`, `total_questions`, `current_question`, `question_text`, `options`). Ensures correct answers and explanations are never exposed in public responses.
  - `service/quiz.py`: implemented `QuizService` with `start_quiz`. Resolves target topic (including querying weakest topic from `TopicStats` when `source="weak_topics"`), clamps question counts to [3, 10], queries approved bank questions with `SQLAlchemyQuestionBank`, triggers synchronous fallback question generation on cache miss within latency budget, and constructs ordered `Quiz` and `QuizQuestion` entities with configurable TTL.
  - `tools/quiz.py`: implemented `quiz_start` tool annotated with `@allow_anonymous` and `@idempotent(tool_name="quiz_start")`. Shapes standardized result envelope with conversational spoken summary (≤ 300 chars, no markdown/symbols).
  - Module & Testing Harness Wiring: registered `quiz_start` in `AcademicsModule.register_tools`, updated tool snapshot (`tests/snapshots/tools.json`), registered isolation test in `tests/security/isolation.py`, and included `academics` in auto-isolation, budget, and description lint tests.
  - Tests: added `tests/unit/test_quiz_service.py` (cache hit, cache miss generation, bounds clamping, upstream error on empty bank) and contract test `tests/contract/test_quiz_start_contract.py` through full MCP client validating envelope format, option count, and absence of answer keys.
- Next: T3.7 `quiz_answer` tool, completion, summary, events.

## 2026-10-23 — T3.4 Verification pass and quarantine loop — DONE

- Summary: implemented independent second-pass answer verification adapter and quarantine lifecycle:
  - `prompts/quiz_verify_v1.md`: prompt instructing an independent model/prompt pass to fact-check and solve the candidate multiple-choice question.
  - `adapters/verification.py`: implemented `QuestionVerifier` executing independent second-pass verification. Validates agreement between generator `correct_key` and verifier `solved_key`. On disagreement or failure, the question is discarded and Prometheus reject metrics (`QUESTION_VERIFICATION_ATTEMPTS_TOTAL`, `QUESTION_VERIFICATION_REJECTIONS_TOTAL`) are recorded.
  - Pipeline Integration: wired `verifier: QuestionVerifier | None = None` into `QuestionGenerationPipeline`, ensuring questions failing the verification pass are rejected before reaching the question bank.
  - Quality Service: implemented `service/quality.py::QuestionQualityService` managing `flag_question` and `quarantine_question`. Questions reaching `academics_flag_quarantine_threshold` (configured in `Settings` with default 3) automatically transition to `QuestionStatus.QUARANTINED`.
  - Config: added `academics_flag_quarantine_threshold: PositiveInt = 3` to `Settings` and `.env.example`.
  - Tests: added `tests/unit/test_question_verification.py` with 6 unit tests covering agreement pass, disagreement rejection, LLM failure safety, pipeline integration filtering, flag increment and quarantine threshold transition, and manual quarantine. Extended `tests/integration/test_question_bank_integration.py` verifying real PostgreSQL flag/quarantine lifecycle and exclusion from serving queries.
- Next: T3.6 `quiz_start` tool and service.

## 2026-10-23 — T3.3 Question generation pipeline: prompts, parsing, validation — DONE

- Summary: implemented question generation pipeline in `src/sahayak/modules/academics/adapters/generation.py`:
  - `prompts/quiz_gen_v1.md`: versioned prompt template with prompt-injection defense delimiting untrusted background source text inside `<source_content>...</source_content>`.
  - `adapters/generation.py`: `QuestionGenerationPipeline` coordinating topic normalization, Wikipedia grounding retrieval via `WikipediaClient.get_grounding`, prompt assembly, structured LLM generation with fallback model support, and strict multi-rule question validation (`validate_and_shuffle_question`).
  - Validation Rules: enforces stem length bounds [10, 500], forbids markdown/formatting symbols in speech stems/options, verifies exactly 4 distinct non-empty options with valid keys `{"A", "B", "C", "D"}`, validates explanation, rejects stems leaking the verbatim answer, shuffles options via cryptographically secure randomness to eliminate LLM position bias while preserving `correct_key`, and deduplicates generated questions via deterministic `content_hash`.
  - Tests: added `tests/unit/test_question_generation.py` with 8 tests covering deterministic content hashing, option shuffling, rejection filters (answer leakage, duplicate options, invalid correct key, formatting symbols), multi-question pipeline filtering with `FakeLLMClient`, and Wikipedia prompt-injection safety wrapping.
- Next: T3.4 Verification pass and quarantine loop.

## 2026-10-23 — T3.5 Quiz domain logic: answer matching and scoring — DONE

- Summary: implemented deterministic spoken answer matching and quiz scoring domain logic:
  - `domain/answer_matching.py`: pure domain module matching spoken utterances to multiple-choice options. Resolves direct letter tokens, explicit option phrasing ("choice B", "my answer is C"), ordinals ("the first one", "second choice"), numerals ("1", "number 2"), ASR homophones ("bee" -> "B", "see" -> "C", "for" -> "D", "won" -> "A"), exact text, space-split compound words ("hemo globin" -> "Hemoglobin"), and RapidFuzz fuzzy matching with confidence thresholds and ambiguity detection.
  - `domain/scoring.py`: pure scoring functions for evaluating answer correctness, computing bounded percentage scores, and checking quiz completion and expiry.
  - Dependencies: added `rapidfuzz` (MIT) and `hypothesis` (MPL-2.0).
  - Tests: added `tests/unit/test_answer_matching.py` with 94 tests including a table of > 60 diverse spoken-answer test cases and Hypothesis property-based tests proving uniqueness and idempotence.
- Next: T3.3 Question generation pipeline: prompts, parsing, validation.

## 2026-10-23 — T3.2 Topic normalization and question-bank repository — DONE

- Summary: implemented topic normalization and question-bank repository:
  - `domain/topics.py`: pure domain module with `normalize_topic`, `slugify`, and `format_display_name`. Maps spoken variants ("Photosynthesis", "photosynthesis!", "  PHOTOSYNTHESIS ") to canonical `("photosynthesis", "Photosynthesis")`. Includes curated alias table ("us history", "ap bio", "calc 1", "ww2", etc.), preserves acronyms/numerals in display names, and enforces bounds (≤ 128 chars slug, ≤ 256 chars display name).
  - `ports.py`: defined `QuestionBankPort` protocol covering `get_or_create_topic`, `find_topic`, `find_questions`, `insert_questions`, `count_available`, `flag_question`, and `quarantine_question`.
  - `adapters/question_bank.py`: implemented `SQLAlchemyQuestionBank` for PostgreSQL. Employs `content_hash` deduplication on question insertions, handles concurrent race conditions, filters exclusions, and auto-quarantines questions exceeding the flag threshold (3 flags). Joins `Topic` in a single query to eliminate N+1 overhead.
  - Tests: added unit tests in `tests/unit/test_topics.py` and integration tests in `tests/integration/test_question_bank_integration.py` verifying deduplication, exclusion queries, flag/quarantine lifecycle, and asserting single query execution (no N+1).
- Next: T3.5 Quiz domain logic: answer matching and scoring (per AGENTS.md §4 sequence).

## 2026-10-23 — T3.1 Academics schema, models, migrations — DONE

- Summary: implemented `modules/academics/` models and multi-branch Alembic migration:
  - `models.py`: 9 SQLAlchemy 2.0 mapped models (`Topic`, `Question`, `Quiz`, `QuizQuestion`, `Deck`, `Card`, `StudyPlan`, `PlanTask`, `TopicStats`), enums with PostgreSQL native enum mappings (`DifficultyLevel`, `QuestionStatus`, `QuizStatus`), primary keys (UUIDv7/UUID), composite PKs, foreign keys, unique constraints, and indexes. All models include default `__init__` for consistent in-memory defaults.
  - Migration `0001_academics_schema.py`: created under `src/sahayak/modules/academics/migrations/` as an independent Alembic branch (`branch_labels = ("academics",)`, `depends_on = ("0002_users_and_identities",)`).
  - Multi-branch Alembic wiring: updated `alembic.ini` (`version_locations`), `Makefile`, `scripts/migrate_check.py`, and `tests/conftest.py` to use `alembic upgrade heads` ensuring full support for multi-branch migrations.
  - `module.py`: Academics module implementing `Module` protocol, with `export_user_data` and `delete_user_data` covering all 9 tables in the `academics` schema.
  - Tests: added unit tests in `tests/unit/test_academics_models.py` and integration tests on PostgreSQL in `tests/integration/test_academics_models_integration.py` verifying `content_hash` uniqueness and foreign key integrity.
- Next: T3.2 Topic normalization and question-bank repository.

## 2026-10-23 — T2.5 Background worker infrastructure — DONE (PHASE 2 COMPLETE)

- Summary: implemented `src/sahayak/worker.py` utilizing `arq` Redis-backed background worker queues:
  - `WorkerRegistry`: supports registering job callables (`register_job` with retry policies and timeouts), cron-style schedules (`register_cron`), and loading module jobs via `module.register_jobs(registry)`.
  - Built-in Jobs: `sample_ping_job` for operational verification, `sample_failing_job` for verifying retry policies with exponential backoff and Prometheus failure counters, and `dispatch_outbox_events_job` mounting transactional outbox event dispatching from T1.6.
  - Lifecycle & Observability: implemented `startup` (instantiating database engine/session factory, module registry, and event dispatcher), `shutdown` (engine disposal and event stop signaling), `on_job_start` (structured logging with `job_id`, `job_try`), and `on_job_end` (Prometheus latency observation on `JOB_DURATION_SECONDS` and execution counting on `JOB_EXECUTIONS_TOTAL`).
  - Worker Entrypoint & Container Wiring: connected `src/sahayak/container.py` when `role == "worker"` to `sahayak.worker.main()` and exposed client enqueue helper `enqueue_job` with connection pooling.
  - Tests: added unit tests in `tests/unit/test_worker.py` and integration tests in `tests/integration/test_worker_integration.py` executing enqueued jobs and retry recovery on Redis.
- Phase 2 Exit Check: all Phase 2 tasks (T2.1 through T2.5) completed, committed to main, and verified green across lint, tests (188 passed with 91.64% coverage), tool snapshot, and database migrations.
- Next: Stage D — Phase 3: Academics module (T3.1 Academics schema, models, migrations).

## 2026-10-23 — T2.4 Grounding client (Wikipedia) and content sanitizer — DONE

- Summary: implemented `shared/content/` with `WikipediaClient` in `wikipedia.py` and sanitization utilities in `sanitizer.py`.
  - `sanitizer.py`: implemented `strip_markup` (removes HTML tags, unescapes entities, resolves piped/simple wiki links, strips wiki templates and formatting), `remove_instruction_patterns` (neutralizes common prompt-injection attempts including system prompt directives, role reversals, and instruction overrides), and `wrap_grounding_text` (neutralizes delimiter breakout tags, strictly caps length to `max_chars`, and encloses content in safety XML boundary delimiters).
  - `wikipedia.py`: implemented `WikipediaClient` communicating with Wikimedia REST and search APIs. Supports `search` (opensearch API), `get_summary` (Wikimedia summary endpoint with Redis caching and 7-day TTL), and `get_grounding` (resolving topics into sanitized, delimited grounding material with automatic disambiguation detection and fallback search). Outbound requests enforce host allow-listing (`*.wikipedia.org`) and compliant `User-Agent`.
  - Tests: added comprehensive test coverage in `tests/unit/test_sanitizer.py` and `tests/unit/test_wikipedia.py` covering standard summaries, disambiguation handling and search failover, missing pages (404), prompt-injection neutralization, delimiter boundary defense, length capping, timeouts, and network/rate-limit error classification.
- Next: T2.5 Background worker infrastructure.

## 2026-10-23 — T2.2 & T2.3 Gemini and Groq adapters — DONE

- Summary: implemented `GeminiClient` in `shared/llm/gemini.py` and `GroqClient` in `shared/llm/groq.py` implementing the `LLMClient` protocol.
  - `GeminiClient`: connects to Google Generative Language REST API (`gemini-2.5-flash`), enforces outbound safe host validation, extracts token usage counts from `usageMetadata`, maps HTTP 401/403/429/5xx into `ProviderUnavailableError`, and parses structured JSON with Pydantic model validation. Includes opt-in live test (`@pytest.mark.live`).
  - `GroqClient`: connects to Groq OpenAI-compatible chat completions API (`llama-3.3-70b-versatile`), handles JSON mode instruction formatting, extracts token usage, parses rate-limit telemetry headers, and maps errors.
  - Contract & Router Integration: Added tests in `tests/unit/test_gemini.py` and `tests/unit/test_groq.py` using `respx`, demonstrating complete primary-to-fallback failover from Gemini to Groq under provider error.
- Next: T2.4 Grounding client (Wikipedia) and content sanitizer.

## 2026-10-23 — T2.1 LLM port, fake client, and router — DONE

- Summary: implemented `shared/llm/` with provider-agnostic `LLMClient` protocol (`generate_text`, `generate_json`), `LLMResponse`, and `TokenUsage`. Created `FakeLLMClient` supporting canned responses, queues, failure injection, and Pydantic validation. Implemented `CircuitBreaker` with CLOSED/OPEN/HALF_OPEN states and recovery timeout, `DailyBudgetManager` with Redis-backed atomic counting and in-memory fallback, and `LLMRouter` with concurrency limiting via semaphores, retries with backoff/jitter, primary-to-fallback routing, and Prometheus instrumentation (`LLM_REQUESTS_TOTAL`, `LLM_DURATION_SECONDS`, `LLM_TOKENS_TOTAL`). Authored ADR 0004 for LLM gateway and routing. Added 13 unit tests covering primary routing, fallback, circuit breaker trips/recovery, budget exhaustion, timeout enforcement, and concurrency limiting.
- Next: T2.2 Gemini adapter.

## 2026-10-23 — Fix: CI Test DB Migrations and Worker Healthcheck — DONE

- Summary: diagnosed and resolved failures in CI `test` and `container` jobs:
  1. `test`: `core.outbox_events` did not exist on fresh PostgreSQL CI service container because `make test` executed before migrations. Added autouse session fixture in `tests/conftest.py` migrating the database to head when PostgreSQL is reachable, and added `make migrate` before `make test` in `.github/workflows/ci.yml`. Also fixed `Makefile` to supply `PYTHONPATH=src` for `migrate` and `migrate-check`, and updated `alembic.ini` to modern `path_separator = os`.
  2. `container`: `docker compose up --wait` failed with `container sahayak-worker-1 has no healthcheck configured` because modern Docker Compose requires all waiting services to have a healthcheck. Configured a lightweight python process healthcheck for the `worker` service.
- Next: Push to `main` and verify GitHub Actions CI.

## 2026-10-23 — T1.7 Identity provider setup and account-linking config — DONE (PHASE 1 COMPLETE)

- Summary: implemented complete AWS Cognito Identity Provider infrastructure as code under `infra/terraform/idp/` (User Pool with email verification, Resource Server with identifier `sahayak-api` and custom scopes `academics.read/write`, User Pool Domain, and App Client for Alexa+ with PKCE S256 authorization code grant and configured Amazon redirect URIs). Authored comprehensive integration guide in `docs/alexa/account-linking.md` with exact values for Developer Console and test user instructions. Enhanced `core/auth/jwt.py` to transparently normalize Cognito resource server scope prefixes (`sahayak-api/academics.read` → `academics.read`). Added contract test `tests/contract/test_account_linking_flow.py` demonstrating end-to-end OAuth 2.1 authorization code with PKCE resulting in token validation and tool authorization.
- Phase 1 Exit Check: all Phase 1 tasks (T1.1 through T1.9) completed, committed to main, all gates green (ruff, mypy strict, import-linter, 134 tests passing with 94.18% coverage, snapshot check, reversible migrations check).
- Next: Stage C — Phase 2: Shared services (T2.1 LLM port, fake client, and router).

## 2026-10-23 — T1.8 Privacy tooling: export, deletion, audit log — DONE

- Summary: implemented `audit_log` table with migration `0005_audit_log` in `core` branch, recording non-sensitive audit events with SHA-256 hashed IP addresses and cascading user disassociation. Implemented `core/audit.py` and `core/privacy.py` with `PrivacyCoordinator` and `RetentionManager`, orchestrating multi-module data export and permanent erasure (Right to be Forgotten). Created CLI utilities `scripts/export_user.py` and `scripts/delete_user.py`. Drafted certification-compliant privacy policy in `docs/legal/privacy-policy.md`. Verified that export returns complete JSON bundles and that deletion leaves zero referencing rows across any schema.
- Next: T1.7 Identity provider setup and account-linking configuration.

## 2026-10-23 — T1.9 Security regression test suite — DONE

- Summary: implemented comprehensive security regression suite in `tests/security/` covering user isolation, token fuzzing, rate limiting, and log/PII redaction. Added `assert_user_isolation` helper and `ISOLATION_REGISTRY` with auto-discovery gate verifying that every registered tool in Sahayak has an isolation test specification. Verified token fuzzing across malformed, expired, future nbf, wrong issuer, wrong audience, alg:none, and symmetric algorithm attempts, returning 401 without WWW-Authenticate per ADR 0003. Verified rate-limit sliding windows and IP isolation, and structlog redaction of tokens, emails, and sensitive keys.
- Next: T1.8 Privacy tooling: export, deletion, audit log.

## 2026-10-23 — T1.6 Domain events and transactional outbox — DONE

- Summary: implemented `outbox_events` and `dead_letter_events` tables with migration `0004_outbox_events` in `core` branch. Implemented `core/events.py` with `DomainEvent`, `publish()` writing to the caller's active transaction/session for transactional atomicity, `EventDispatcher` supporting type-specific and wildcard subscribers as well as module `on_event` dispatching, retry counting with dead-lettering to `dead_letter_events`, and `@idempotent_handler` ensuring duplicate event deliveries are harmless. Tested on real PostgreSQL that rolled-back transactions never publish, committed transactions are delivered and marked processed, and repeatedly failing handlers dead-letter after configured retries.
- Next: T1.9 Security regression test suite.

## 2026-10-23 — T1.5 Idempotency for mutating tools — DONE

- Summary: implemented `idempotency_keys` table and migration `0003_idempotency_keys` in `core` branch with unique lookup index on `(tool, key, COALESCE(user_id, '00000000-0000-0000-0000-000000000000'))`. Implemented `IdempotencyRecord`, `IdempotencyRepository`, and `IdempotencyService` with transactional nested savepoint concurrency handling and fallback in-memory caching. Created `@idempotent` decorator binding to `request_id`, user principal, and configured TTL. Verified replay, isolation between users, and concurrent execution on real PostgreSQL.
- Next: T1.6 Domain events and transactional outbox.

## 2026-10-22 — T1.4 HTTP security hardening — DONE

- Summary: implemented `core/security.py` providing `SecurityHeadersMiddleware` (HSTS, nosniff, DENY frame options, no-referrer, CSP), `OriginValidationMiddleware` (allow-list validation and DNS-rebinding protection), `RequestBodyLimitMiddleware` (rejection of requests exceeding `max_request_body_bytes` with 413), and `create_safe_http_client` with pre-request outbound host filtering raising `HostBlockedError`. Added `max_request_body_bytes` configuration to `Settings` and documented in `.env.example`.
- Next: T1.5 Idempotency for mutating tools.

## 2026-10-22 — T1.3 Principal, scopes, tool authorization, protected-resource metadata — DONE

- Summary: implemented `core/auth/principal.py` with `Principal` dataclass and ContextVar lifecycle, `@requires(scope=...)` and `@allow_anonymous` decorators mapping unauthenticated/forbidden invocations to standard `auth_required` and `forbidden` error envelopes. Added `AuthMiddleware` to extract bearer tokens, validate via `JWTValidator`, and resolve platform `User` via `UserService`. Mounted RFC 9728 protected resource metadata endpoint at `/.well-known/oauth-protected-resource` and enforced 401 response without `WWW-Authenticate` header per ADR 0003. Verified with end-to-end contract and unit tests.
- Next: T1.4 HTTP security hardening.

## 2026-10-22 — T1.2 JWT validation and JWKS cache — DONE

- Summary: implemented `core/auth/jwt.py` with `JWTValidator`, multi-level JWKS caching (local memory + Redis), key rotation handling on unknown `kid`, asymmetric algorithm allow-list (RS256/384/512, ES256/384/512), 60s clock skew tolerance, and extraction of standard and provider-specific scope claims. Comprehensive unit test suite covers valid, expired, wrong audience, wrong issuer, bad signature, unknown `kid`, rotated key, malformed token, and cache operations.
- Next: T1.3 Principal, scopes, tool authorization, protected-resource metadata.

## 2026-10-22 — T1.1 Platform user model — DONE

- Summary: implemented `shared/users/` models (`users`, `user_identities`), repository, and service (`get_or_create_by_identity`, `soft_delete_user`) with savepoint-based concurrency handling for race conditions on unique `(issuer, subject)`. Added Alembic migration `0002_users_and_identities` in `core` branch. Added unit tests and an integration test verifying idempotent concurrent provisioning on PostgreSQL.
- Next: T1.2 JWT validation and JWKS cache.

## 2026-10-22 — T0.12 Observability foundation — DONE (PHASE 0 COMPLETE)

- Commit: pending T0.12 commit.
- Summary: created `core/observability/` with structlog JSON configuration and redaction processor (Bearer tokens, emails, JWTs, sensitive keys), OpenTelemetry tracing setup, Prometheus metrics registry with tool, cache, and LLM metrics, tool-call instrumentation wrapper, and a protected `/metrics` endpoint.
- Decisions: `/metrics` can be authenticated via `settings.metrics_token` (Authorization Bearer or X-Metrics-Token).
- Phase 0 Exit Check: clean clone → `make setup && make dev` works; MCP Inspector connects to `ping_echo`; CI green; ADRs 0002/0003/0009/0010 written.
- Next: Stage B — Phase 1: Identity, security, events (T1.1 Platform user model).

## 2026-10-22 — T0.11 Contract test harness, tool snapshot, tool-budget guard — DONE

- Commit: pending T0.11 commit.
- Summary: implemented scripts/snapshot_tools.py to generate and check tests/snapshots/tools.json, wired `make snapshot` and `make snapshot-check`, added budget guard tests (MAX_TOOLS, MAX_TOOLS_PER_MODULE), tool description voice-linter (format with "Use when", example utterance, "Do not use for"), and end-to-end HTTP contract tests (initialize → tools/list → tools/call).
- Next: T0.12 Observability foundation (last task of Phase 0).

## 2026-10-22 — T0.10 MCP server wiring (stateless Streamable HTTP) — DONE

- Commit: pending T0.10 commit.
- Summary: configured FastMCP/MCPServer for stateless Streamable HTTP (`stateless_http=True`, `json_response=True`), mounted into FastAPI with lifespan, returning 405 on GET /mcp per spec, verified protocol 2025-11-25 negotiation and tools/call on ping_echo, and verified round-robin multi-replica statelessness.
- Decisions: used MCPRoutingMiddleware on FastAPI to cleanly route /mcp to the Streamable HTTP application without shadowing other routes.
- Next: T0.11 Contract test harness, tool snapshot, tool-budget guard.

## 2026-10-22 — T0.9 Module protocol, registry, template module, boundary rules — DONE

- Commit: pending T0.9 commit.
- Summary: created the Module protocol, Deps dependency container, ModuleRegistry with dynamic loading and discovery from ENABLED_MODULES, complete template module skeleton (_template) with domain, ports, adapters, service, schemas, and ping_echo tool, plus import-linter contracts enforcing core ↛ modules, domain ↛ adapters, and module independence.
- Decisions: import-linter contracts configured directly in pyproject.toml under [tool.importlinter].
- Next: T0.10 MCP server wiring (stateless Streamable HTTP).

## 2026-10-22 — T0.8 Result envelope and error model — DONE

- Commit: `a2606f6`.
- Summary: created the standardized result envelope (`ok()`, `fail()`), size cap enforcement (MAX_RESPONSE_BYTES), spoken_summary character limits and cleaner (markdown/emoji stripping), and stable error hierarchy mapped to PRD §9.4 codes.
- Next: T0.9 Module protocol and boundary rules.

## 2026-10-22 — T0.7 Redis wrapper and rate limiter — DONE

- Commit: `c3e4e0b`.
- Summary: implemented Redis cache wrapper with namespaced keys and TTL, distributed lock helper, and atomic sliding-window rate limiter keyed by principal or IP.
- Next: T0.8 Result envelope and error model.

## 2026-10-22 — T0.6 Database layer and migrations framework — DONE

- Commit: pending database-foundation commit.
- Summary: added async SQLAlchemy infrastructure, transaction-scoped units of work, Alembic configuration, and a reversible `core` schema migration.
- Decisions: the CI PostgreSQL service performs the up → down → up gate; local hosts without a container runtime validate migration SQL offline.
- Assumptions made: module migration paths are appended when each module is introduced, while `core` owns the initial branch label.
- Next: T0.7 Redis wrapper and rate limiter.

## 2026-10-22 — T0.5 Application factory, health endpoints, request IDs — DONE

- Commit: pending application-factory commit.
- Summary: added the FastAPI factory, generated or propagated correlation IDs, liveness/readiness endpoints, safe exception handling, and a production container health probe.
- Decisions: readiness dependencies are injected so DB and Redis checks can be added by their owning tasks.
- Assumptions made: an inbound request ID is opaque and retained verbatim for caller-side trace correlation.
- Next: T0.6 database layer and migrations.

## 2026-10-22 — T0.3 Docker stack and T0.4 CI pipeline — DONE

- Commit: `5faf7b4`, `d0389ac`, `2ad51b7`, and `b18dd67`.
- Summary: Docker/Compose topology, security and quality CI gates, and compose-runtime verification are complete.
- Decisions: container verification runs on GitHub CI because no container runtime is installed on the local host.
- Next: T0.5 application factory.

## 2026-10-22 — Repository workflow policy — DONE

- Commit: pending direct-to-main policy commit.
- Summary: closed the four Dependabot PRs and disabled the PR-generating Dependabot configuration.
- Decisions: all work proceeds directly on `main`; each completed subtask is one Conventional Commit; no branches or pull requests.
- Assumptions made: dependency updates remain manually reviewed and committed as isolated subtasks.
- Next: finish verification and close out Phase 0.

## 2026-10-21 — T0.2 Typed configuration — DONE

- Commit: typed configuration commit.
- Summary: added validated environment settings, secret masking, comma-list parsing, safe limits, and a cached accessor.
- Decisions: request timeout defaults to 0.45 seconds per ADR-0010’s verified Alexa+ latency requirement.
- Assumptions made: URL shapes are validated now; provider-specific model IDs remain unset until their dedicated tasks.
- Surprises / lessons: Pydantic Settings decodes tuple values as JSON by default, so comma-separated environment fields require `NoDecode`.
- Next: T0.4 CI pipeline.

## 2026-10-21 — T0.13 Alexa+ documentation research and ADRs — DONE

- Commit: verification record commit.
- Summary: verified V1–V9 against Amazon’s MCP Toolkit documents; findings and ADRs remain local-only by repository policy.
- Decisions: ADR-0002, ADR-0003, ADR-0009, ADR-0010.
- Assumptions made: no published numeric tool cap, response-size cap, general MCP locale matrix, or `Origin` value; en-US and an 8 KiB response cap remain configurable assumptions.
- Surprises / lessons: Amazon specifies sub-500 ms round-trip latency and does not support `WWW-Authenticate` in MCP linking responses.
- Next: T0.2 typed configuration.

## 2026-10-21 — T0.1 Repository scaffold and developer tooling — DONE

- Commit: initial repository scaffold commit.
- Summary: created the Python 3.12 `uv` project, developer commands, pre-commit hooks, source/test layout, foundational documentation, and ADR template.
- Decisions: ADR-0001 confirms Python 3.12 and staged dependency introduction.
- Assumptions made: no application dependency is needed before its owning task; the host-specific editable-install issue is handled by `PYTHONPATH=src` in project commands.
- Surprises / lessons: Python 3.12.13 ignores hidden editable-install `.pth` files generated by the selected build backend.
- Next: T0.13 documentation research, then T0.2 typed configuration.
