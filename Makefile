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
	@echo "Tool snapshots are introduced by T0.11."

snapshot-check:
	@echo "Tool snapshot checks are introduced by T0.11."

tunnel:
	cloudflared tunnel --url http://localhost:8000

inspector:
	npx @modelcontextprotocol/inspector http://localhost:8000/mcp
