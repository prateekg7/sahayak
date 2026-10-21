"""Static checks for local container configuration."""

from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_dockerfile_runs_as_non_root_and_has_a_healthcheck() -> None:
    """Require the image to drop privileges and expose a health check."""
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "FROM python:${PYTHON_VERSION}-slim-bookworm AS builder" in dockerfile
    assert "FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime" in dockerfile
    assert "USER sahayak" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "uv sync --frozen --no-dev" in dockerfile


def test_compose_defines_the_local_runtime_topology() -> None:
    """Require app, worker, PostgreSQL 16, Redis 7, and durable volumes."""
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    for expected in (
        "  app:",
        "  worker:",
        "  postgres:",
        "postgres:16-bookworm",
        "  redis:",
        "redis:7-bookworm",
        "postgres_data:",
        "redis_data:",
    ):
        assert expected in compose
