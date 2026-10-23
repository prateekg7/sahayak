# Module Authoring Guide

This guide describes how to create and register a new capability module in Sahayak (e.g. `productivity`, `finance`, `health`).

---

## 1. Module Architecture & Folder Structure

All modules live in `src/sahayak/modules/<module_name>/` and are cloned from `src/sahayak/modules/_template/`:

```
src/sahayak/modules/<module_name>/
├── __init__.py
├── api.py           # Public cross-module protocol & service
├── domain/          # Pure domain logic (zero I/O, no framework imports)
├── ports.py         # Repository & service interfaces
├── adapters/        # Database repositories & external adapters
├── models.py        # SQLAlchemy table models
├── migrations/      # Alembic schema migrations
├── schemas.py       # Pydantic request/response models
├── service/         # Business orchestration & transaction management
├── tools/           # Thin MCP tool endpoints
└── module.py        # Module lifecycle & registration
```

---

## 2. Step-by-Step Implementation Workflow

### Step 1: Copy Template
```bash
cp -r src/sahayak/modules/_template src/sahayak/modules/<module_name>
```

### Step 2: Define Schema & Migrations
1. Define SQLAlchemy models in `models.py` with explicit schema:
   ```python
   __table_args__ = {"schema": "<module_name>"}
   ```
2. Create Alembic migration in `migrations/` ensuring:
   - Primary keys use UUIDv7/ULID.
   - Timestamps use `timestamptz` with UTC.
   - Foreign keys and constraints are enforced in the database.
   - Downgrade script is clean and reversible.

### Step 3: Implement Pure Domain Logic
- Place business calculations (e.g. scoring, scheduling, streaks, money arithmetic) in `domain/`.
- Domain code must import **nothing** from SQLAlchemy, FastAPI, or MCP.

### Step 4: Implement Service Layer
- Orchestrate database transactions using the Unit-of-Work pattern.
- Take `user_id` as explicit parameter on all user-scoped operations.
- Publish outbox domain events using `EventPublisher`.

### Step 5: Implement Thin MCP Tools
- Each tool lives in `tools/<tool_name>.py`.
- Formatted description:
  1. One sentence of what it does.
  2. "Use when..." with quoted example utterance.
  3. "Do not use for..." pointing to sibling tools.
- Decorate with `@requires()` (or `@allow_anonymous` if public).
- Mutating tools must accept `request_id` and use `@idempotent`.
- Return standard response envelope (`ok`, `spoken_summary`, `data`, `next_actions`).
- Spoken summary must be $\le 300$ chars, free of markdown and raw URLs.

### Step 6: Implement Module Lifecycle (`module.py`)
- Subclass `BaseModule` (implements `Module` protocol).
- Register tools in `register_tools(server)`.
- Implement `export_user_data(user_id)` and `delete_user_data(user_id)` covering all module tables.
- Expose cross-module capabilities through `api` property.

### Step 7: Update Tool Budget & Snapshot
- Run `make snapshot` to update `tests/snapshots/tools.json`.
- Add tool isolation spec in `tests/security/isolation.py`.
- Verify contracts: `make lint test snapshot-check migrate-check`.
