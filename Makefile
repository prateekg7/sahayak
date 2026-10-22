.PHONY: setup dev test lint typecheck migrate migrate-check snapshot snapshot-check tunnel inspector

setup:
	uv sync --all-groups
	uv run pre-commit install

dev:
	docker compose up --build --remove-orphans

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
	uv run alembic upgrade head

migrate-check:
	uv run python scripts/migrate_check.py

snapshot:
	PYTHONPATH=src uv run python scripts/snapshot_tools.py

snapshot-check:
	PYTHONPATH=src uv run python scripts/snapshot_tools.py --check

tunnel:
	cloudflared tunnel --url http://localhost:8000

inspector:
	npx @modelcontextprotocol/inspector http://localhost:8000/mcp
