# Sahayak Developer Guide

This guide provides deep technical instructions for developing, debugging, testing, and operating the Sahayak platform.

---

## 1. Local Environment Setup

### Tools Required
- **Python 3.12:** Managed via [uv](https://github.com/astral-sh/uv).
- **PostgreSQL 16:** Available locally or via Docker Compose.
- **Redis 7:** Available locally or via Docker Compose.

### Quick Setup
```bash
# Sync all virtualenv dependencies
uv sync --all-groups

# Install git pre-commit hooks
uv run pre-commit install
```

---

## 2. Running Services Locally

### Full Docker Compose Stack
```bash
make dev
```
Starts:
- FastAPI Web Server: `http://localhost:8000`
- Arq Background Worker: polling `sahayak_jobs` queue
- PostgreSQL 16: `localhost:5432` (`sahayak`/`sahayak`)
- Redis 7: `localhost:6379`

### Running the Python Application Natively
```bash
# Apply database migrations
make migrate

# Run MCP Web Server
uv run uvicorn sahayak.main:create_app --factory --port 8000 --reload

# Run Background Worker (separate terminal)
uv run python -m sahayak.worker
```

---

## 3. Database Management & Migrations

Alembic manages database migrations with schema separation. Each module owns its schema (e.g. `core`, `academics`).

```bash
# Apply pending migrations
make migrate

# Test migration reversibility (upgrade -> downgrade -> upgrade)
make migrate-check

# Create a new revision for a module
uv run alembic revision -m "add_my_table" --version-path src/sahayak/modules/<module>/migrations
```

*Important:* In production, migrations are executed using the `sahayak_migrator` role. The runtime application user `sahayak_app` has DML privileges only (cannot run `CREATE` or `DROP TABLE`).

---

## 4. Testing & Quality Assurance

Sahayak follows the test pyramid:
1. **Unit Tests:** Fast, isolated, zero network I/O (`tests/unit/`). Uses `FakeLLMClient` and deterministic fake clocks.
2. **Integration Tests:** Verifies real database queries and outbox events against Postgres and Redis (`tests/integration/`).
3. **Contract Tests:** Replays voice turn scenarios through the MCP client over Streamable HTTP (`tests/contract/`).
4. **Security Tests:** Validates cross-user tenant isolation on every registered tool (`tests/security/`).

Run the full test suite with coverage enforcement:
```bash
make test
```
Minimum coverage threshold is strictly enforced at 85%.

---

## 5. Tool Snapshot Verification

Public MCP tool signatures are tracked in `tests/snapshots/tools.json`. Any tool addition or signature change requires an explicit snapshot update:
```bash
# Verify current tools match snapshot
make snapshot-check

# Regenerate snapshot (only when tool changes are intentional)
make snapshot
```
*Note:* Modifying public tool signatures requires an Alexa+ add-on manifest redeployment (`alexa-ai deploy`).
