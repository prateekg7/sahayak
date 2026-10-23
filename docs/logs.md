# Engineering log

## 2026-10-22 — T0.6 Database foundation — done

### Completed

- Added SQLAlchemy async engine/session factories, declarative metadata naming conventions, and the Unit-of-Work helper.
- Added Alembic async configuration and a reversible `core` branch migration that creates the `core` PostgreSQL schema.
- Added `make migrate` and `make migrate-check`; CI runs the full upgrade → downgrade → upgrade sequence against PostgreSQL 16.

### Verification

- `make lint test` passes: 21 tests at 94.20% coverage.
- Offline migration generation contains `CREATE SCHEMA core` and validates the graph without a database connection.

## 2026-10-22 — T0.5 Application factory — done

### Completed

- Added the FastAPI application factory, `/healthz`, and an injectable `/readyz` dependency-check mechanism.
- Added `X-Request-ID` propagation using a sortable ULID for requests without a caller-provided ID.
- Added a safe global exception response that includes only a generic message and correlation ID.
- Replaced the Docker import-only probe with an HTTP `/healthz` probe and runs the app through Uvicorn.

### Verification

- `make lint test` passes: Ruff, strict Mypy, import-linter, and 18 tests at 94.97% coverage.

## 2026-10-22 — Source-control policy changed to direct commits

### Completed

- Reviewed and closed the four automated Dependabot pull requests: #2, #4, #5, and #6. They proposed one GitHub Actions and three development-dependency range updates; none was created by the project workflow.
- Removed `.github/dependabot.yml` so scheduled dependency updates cannot create further pull requests.
- Updated the local-only operating manual and PRD: work happens directly on `main`, with exactly one Conventional Commit per completed subtask; branches and pull requests are prohibited.

### Verification

- Confirmed local and remote tracking state is `main...origin/main` with no local feature branches.

### Follow-up

- Review dependency upgrades manually and apply each as its own committed subtask after local gates pass.

## 2026-10-21 — T0.2 Typed configuration — done

### Completed

- T0.1 repository scaffold committed as `cd006bc`.
- T0.13 Alexa+ documentation verification recorded as empty commit `d1305cd`; its detailed findings and ADRs are local-only.
- Git ignores every Markdown file except `README.md`.
- Added `pydantic-settings` and refreshed `uv.lock`.
- Implemented `sahayak.core.config.Settings`, `AppEnvironment`, validators for module lists, allowed origins, database/Redis schemes, and cached `get_settings()`.
- Added tests for defaults, environment overrides, invalid values, and secret masking.

### Verification so far

- `make setup` completed successfully with Python 3.12.13 and installed `pydantic-settings 2.16.1`.
- Initial `make lint test` passed Ruff but Mypy found explicit URL-default and Pydantic constructor typing issues; those were corrected.
- Final verification passed: Ruff, strict Mypy, import-linter, and 9 unit tests at 100% coverage.

### Remaining

1. Commit only tracked source/configuration/test files; do not add local Markdown records.
2. Continue with T0.4 CI pipeline, which is the next dependency-satisfied bootstrap task.

## 2026-10-22 — T0.3 Docker image and local compose stack — awaiting runtime verification

### Completed

- Added a multi-stage Python 3.12 Dockerfile using pinned `uv 0.11.15`, a minimal runtime stage, an unprivileged `sahayak` user, and an import-level health check that T0.5 will replace with `/healthz`.
- Added `docker-compose.yml` defining app, worker, PostgreSQL 16, Redis 7, health-gated dependencies, durable named volumes, and defaults compatible with the project `.env` convention.
- Added `.dockerignore` to exclude local environments, tests, documentation, and development artifacts from the build context.
- Added a signal-safe bootstrap entry point for the app and worker until T0.5/T2.5 provide their actual runtimes.
- Added unit/static configuration tests; `make lint test` passes: 14 tests, 96% total coverage.

### Blocker

- This host has no `docker`, `podman`, `colima`, `nerdctl`, or `lima` executable. I cannot run `make dev`, build the image, inspect its size, or confirm the container user without a container runtime.
- No runtime has been installed because that is a machine-level change outside the code task.

### Remaining verification

1. Install or make Docker Desktop available on this host.
2. Run `make dev`, confirm app/worker/Postgres/Redis reach healthy state, inspect image size and `docker compose exec app id -u`, then stop the stack.
3. T0.5 adds and verifies `curl localhost:8000/healthz`.
