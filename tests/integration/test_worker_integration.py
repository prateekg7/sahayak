"""Integration tests for background worker executing jobs through Redis (T2.5)."""

from __future__ import annotations

import pytest
from arq.connections import create_pool
from arq.worker import Worker
from redis.asyncio import Redis

from sahayak.core.config import get_settings
from sahayak.worker import (
    get_redis_settings,
    on_job_end,
    on_job_start,
    sample_failing_job,
    sample_ping_job,
)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_worker_executes_enqueued_ping_job() -> None:
    """A sample job enqueued into Redis is picked up and processed by the worker."""
    settings = get_settings()
    redis_client = Redis.from_url(str(settings.redis_url))

    try:
        await redis_client.ping()
    except Exception:
        pytest.skip("Redis is not accessible for worker integration test")
    finally:
        await redis_client.aclose()

    redis_settings = get_redis_settings(settings)
    pool = await create_pool(redis_settings)

    try:
        # 1. Enqueue sample ping job
        job = await pool.enqueue_job("sample_ping_job", "Integration Payload 42")
        assert job is not None

        # 2. Run worker in burst mode to process all queued jobs
        worker = Worker(
            functions=[sample_ping_job],
            redis_settings=redis_settings,
            on_job_start=on_job_start,
            on_job_end=on_job_end,
            burst=True,
            poll_delay=0.05,
        )
        await worker.async_run()

        # 3. Verify job result
        result = await job.result(timeout=5)
        assert result["status"] == "ok"
        assert result["echo"] == "Integration Payload 42"
        assert result["job_id"] == job.job_id
    finally:
        await pool.aclose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_worker_retries_failing_job() -> None:
    """A failing job retries according to policy and executes until recovery."""
    settings = get_settings()
    redis_client = Redis.from_url(str(settings.redis_url))

    try:
        await redis_client.ping()
    except Exception:
        pytest.skip("Redis is not accessible for worker integration test")
    finally:
        await redis_client.aclose()

    redis_settings = get_redis_settings(settings)
    pool = await create_pool(redis_settings)

    try:
        # Enqueue failing job configured to fail on try 1 and recover on try 2
        job = await pool.enqueue_job("sample_failing_job", fail_until_try=1)
        assert job is not None

        worker = Worker(
            functions=[sample_failing_job],
            redis_settings=redis_settings,
            on_job_start=on_job_start,
            on_job_end=on_job_end,
            burst=True,
            poll_delay=0.05,
            max_tries=3,
        )
        await worker.async_run()

        result = await job.result(timeout=5)
        assert result == "recovered"
    finally:
        await pool.aclose()
