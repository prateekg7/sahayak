.PHONY: setup dev run test smoke lint typecheck security migrate migrate-check snapshot snapshot-check tunnel inspector

security:
	uv run bandit --quiet --recursive src
	uv run pip-audit

setup:
	uv sync --all-groups
	uv run pre-commit install

dev:
	docker compose up --build --remove-orphans

run:
	PYTHONPATH=src DEPLOYMENT_PROFILE=full uv run uvicorn sahayak.main:app --host 127.0.0.1 --port 8000 --reload

smoke:
	uv run python scripts/smoke_test.py --url http://127.0.0.1:8000 --iterations 5

test:
	PYTHONPATH=src uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy
	PYTHONPATH=src uv run lint-imports

typecheck:
	uv run mypy

migrate:
	PYTHONPATH=src uv run alembic upgrade heads

migrate-check:
	PYTHONPATH=src uv run python scripts/migrate_check.py

snapshot:
	PYTHONPATH=src uv run python scripts/snapshot_tools.py --all-profiles

snapshot-check:
	PYTHONPATH=src uv run python scripts/snapshot_tools.py --all-profiles --check

tunnel:
	cloudflared tunnel --url http://localhost:8000

inspector:
	npx @modelcontextprotocol/inspector http://localhost:8000/mcp
