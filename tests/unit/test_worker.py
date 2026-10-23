"""Unit tests for background worker registry, lifecycle, and jobs (T2.5)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arq.worker import Retry

from sahayak.core.config import Settings
from sahayak.core.module import ModuleRegistry
from sahayak.core.observability.metrics import JOB_EXECUTIONS_TOTAL
from sahayak.worker import (
    WorkerRegistry,
    dispatch_outbox_events_job,
    get_redis_settings,
    on_job_end,
    on_job_start,
    sample_failing_job,
    sample_ping_job,
    shutdown,
    startup,
)


def test_get_redis_settings() -> None:
    settings = Settings(redis_url="redis://custom-host:6380/2")  # type: ignore[arg-type]
    arq_redis = get_redis_settings(settings)
    assert arq_redis.host == "custom-host"
    assert arq_redis.port == 6380
    assert arq_redis.database == 2


def test_worker_registry_registration() -> None:
    registry = WorkerRegistry()

    async def custom_job(ctx: dict[str, Any], x: int) -> int:
        return x * 2

    async def scheduled_job(ctx: dict[str, Any]) -> None:
        pass

    registry.register_job(custom_job, name="custom_job", max_tries=3, timeout=60)
    registry.register_cron(scheduled_job, minute=0, hour=12, name="scheduled_job")

    funcs = registry.get_functions()
    crons = registry.get_cron_jobs()

    assert len(funcs) == 1
    func_name = getattr(funcs[0], "name", getattr(funcs[0], "__name__", None))
    assert func_name == "custom_job"
    assert len(crons) == 1
    assert crons[0].name == "scheduled_job"


def test_worker_registry_load_modules() -> None:
    registry = WorkerRegistry()
    mock_module = MagicMock()
    mock_module.name = "test_module"

    mod_registry = MagicMock(spec=ModuleRegistry)
    mod_registry.modules = {"test_module": mock_module}

    registry.load_modules(mod_registry)
    mock_module.register_jobs.assert_called_once_with(registry)


@pytest.mark.asyncio
async def test_sample_ping_job() -> None:
    ctx = {"job_id": "test-job-123", "job_try": 1}
    result = await sample_ping_job(ctx, message="hello sahayak")

    assert result["status"] == "ok"
    assert result["echo"] == "hello sahayak"
    assert result["job_id"] == "test-job-123"
    assert result["job_try"] == 1


@pytest.mark.asyncio
async def test_sample_failing_job_retries_and_recovers() -> None:
    ctx = {"job_id": "test-fail-1", "job_try": 1}

    # Try 1 raises Retry
    with pytest.raises(Retry):
        await sample_failing_job(ctx, fail_until_try=2)

    # Try 2 raises Retry
    ctx["job_try"] = 2
    with pytest.raises(Retry):
        await sample_failing_job(ctx, fail_until_try=2)

    # Try 3 succeeds
    ctx["job_try"] = 3
    result = await sample_failing_job(ctx, fail_until_try=2)
    assert result == "recovered"


@pytest.mark.asyncio
async def test_dispatch_outbox_events_job() -> None:
    mock_dispatcher = AsyncMock()
    mock_dispatcher.dispatch_pending.return_value = 5

    ctx = {"event_dispatcher": mock_dispatcher}
    count = await dispatch_outbox_events_job(ctx, batch_size=20)

    assert count == 5
    mock_dispatcher.dispatch_pending.assert_awaited_once_with(batch_size=20)


@pytest.mark.asyncio
async def test_dispatch_outbox_events_job_no_dispatcher() -> None:
    ctx: dict[str, Any] = {}
    count = await dispatch_outbox_events_job(ctx)
    assert count == 0


@pytest.mark.asyncio
async def test_on_job_start_and_end_metrics() -> None:
    ctx: dict[str, Any] = {
        "job_id": "job-metric-456",
        "job_try": 1,
        "function": sample_ping_job,
    }

    await on_job_start(ctx)
    assert "_job_start_time" in ctx
    assert ctx["_job_name"] == "sample_ping_job"

    # Advance time slightly
    metric = JOB_EXECUTIONS_TOTAL.labels(job="sample_ping_job", outcome="success")
    initial_count = metric._value.get()
    await on_job_end(ctx)
    updated_count = metric._value.get()

    assert updated_count == initial_count + 1


@pytest.mark.asyncio
async def test_worker_startup_and_shutdown() -> None:
    ctx: dict[str, Any] = {}

    with (
        patch("sahayak.worker.create_engine") as mock_ce,
        patch("sahayak.worker.create_session_factory") as mock_csf,
        patch("sahayak.worker.ModuleRegistry") as mock_mr_cls,
    ):
        mock_engine = MagicMock()
        mock_engine.dispose = AsyncMock()
        mock_ce.return_value = mock_engine

        mock_factory = MagicMock()
        mock_csf.return_value = mock_factory

        mock_mr = MagicMock()
        mock_mr.modules = {}
        mock_mr_cls.return_value = mock_mr

        await startup(ctx)

        assert "session_factory" in ctx
        assert "module_registry" in ctx
        assert "event_dispatcher" in ctx
        assert "stop_event" in ctx

        await shutdown(ctx)
        assert ctx["stop_event"].is_set()
        mock_engine.dispose.assert_awaited_once()
