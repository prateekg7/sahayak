"""Background worker infrastructure using arq with scheduled jobs and event dispatching."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

import structlog
from arq.connections import ArqRedis, RedisSettings, create_pool
from arq.cron import CronJob, cron
from arq.worker import Function, Retry, create_worker, func

from sahayak.core.config import Settings, get_settings
from sahayak.core.db.session import create_engine, create_session_factory
from sahayak.core.events import EventDispatcher
from sahayak.core.module import ModuleRegistry
from sahayak.core.observability.metrics import JOB_DURATION_SECONDS, JOB_EXECUTIONS_TOTAL

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)


def get_redis_settings(settings: Settings | None = None) -> RedisSettings:
    """Derive arq RedisSettings from application configuration.

    Args:
        settings: Application settings, defaults to process settings.

    Returns:
        Arq-compatible RedisSettings instance.
    """
    cfg = settings or get_settings()
    url = str(cfg.redis_url)
    return RedisSettings.from_dsn(url)


class WorkerRegistry:
    """Registry for discovering and configuring background worker jobs and schedules."""

    def __init__(self) -> None:
        self._functions: dict[str, Function | Callable[..., Any]] = {}
        self._cron_jobs: list[CronJob] = []

    def register_job(
        self,
        handler: Callable[..., Any],
        *,
        name: str | None = None,
        max_tries: int | None = None,
        timeout: int | None = None,
    ) -> None:
        """Register a background job callable with optional retry and timeout limits."""
        job_name = name or handler.__name__
        decorated = func(handler, name=job_name, max_tries=max_tries, timeout=timeout)
        self._functions[job_name] = decorated

    def register_cron(
        self,
        handler: Callable[..., Any],
        *,
        minute: Any = None,
        hour: Any = None,
        day: Any = None,
        month: Any = None,
        weekday: Any = None,
        second: Any = None,
        name: str | None = None,
        run_at_startup: bool = False,
    ) -> None:
        """Register a periodic cron schedule with arq."""
        job_name = name or handler.__name__
        cron_entry = cron(
            handler,
            name=job_name,
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            weekday=weekday,
            second=second,
            run_at_startup=run_at_startup,
        )
        self._cron_jobs.append(cron_entry)

    def load_modules(self, module_registry: ModuleRegistry) -> None:
        """Invoke register_jobs on all loaded modules."""
        for mod in module_registry.modules.values():
            mod.register_jobs(self)

    def get_functions(self) -> list[Function | Callable[..., Any]]:
        """Return list of all registered worker job functions."""
        return list(self._functions.values())

    def get_cron_jobs(self) -> list[CronJob]:
        """Return list of all registered cron jobs."""
        return list(self._cron_jobs)


# Global worker registry instance
worker_registry = WorkerRegistry()


# ---------------------------------------------------------------------------
# Built-in background jobs
# ---------------------------------------------------------------------------


async def sample_ping_job(ctx: dict[str, Any], message: str) -> dict[str, Any]:
    """Sample diagnostic job that returns echoed payload and context metadata."""
    job_id = ctx.get("job_id", "local")
    logger.info("sample_ping_job_executing", message=message, job_id=job_id)
    return {
        "status": "ok",
        "echo": message,
        "job_id": job_id,
        "job_try": ctx.get("job_try", 1),
    }


async def sample_failing_job(
    ctx: dict[str, Any],
    *,
    fail_until_try: int = 2,
    error_message: str = "Simulated worker failure",
) -> str:
    """Sample job for testing retry behavior and failure metric increments."""
    current_try = ctx.get("job_try", 1)
    if current_try <= fail_until_try:
        logger.warning(
            "sample_failing_job_attempt_failed",
            job_try=current_try,
            fail_until_try=fail_until_try,
        )
        # In arq, raising Retry schedules the job for retry up to max_tries
        raise Retry(defer=0.1)

    logger.info("sample_failing_job_succeeded_on_recovery", job_try=current_try)
    return "recovered"


async def dispatch_outbox_events_job(ctx: dict[str, Any], batch_size: int = 50) -> int:
    """Periodic job processing transactional outbox events from T1.6."""
    dispatcher: EventDispatcher | None = ctx.get("event_dispatcher")
    if dispatcher is None:
        logger.warning("event_dispatcher_not_available_in_worker_ctx")
        return 0

    count = await dispatcher.dispatch_pending(batch_size=batch_size)
    if count > 0:
        logger.info("dispatched_outbox_events_batch", count=count)
    return count


# Register standard built-in jobs
worker_registry.register_job(sample_ping_job, name="sample_ping_job")
worker_registry.register_job(sample_failing_job, name="sample_failing_job", max_tries=3)
worker_registry.register_job(dispatch_outbox_events_job, name="dispatch_outbox_events_job")


# ---------------------------------------------------------------------------
# Worker Lifecycle Callbacks
# ---------------------------------------------------------------------------


async def startup(ctx: dict[str, Any]) -> None:
    """Initialize worker dependencies, database session factory, and event dispatcher."""
    settings = get_settings()
    logger.info("worker_startup_starting", app_env=settings.app_env)

    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    ctx["engine"] = engine
    ctx["session_factory"] = session_factory

    # Create module registry and load enabled modules
    module_registry = ModuleRegistry()
    module_registry.load(settings.enabled_modules)
    ctx["module_registry"] = module_registry

    # Load background jobs registered by each feature module
    worker_registry.load_modules(module_registry)

    # Initialize event dispatcher
    event_dispatcher = EventDispatcher(
        session_factory=session_factory,
        registry=module_registry,
    )
    ctx["event_dispatcher"] = event_dispatcher

    stop_event = asyncio.Event()
    ctx["stop_event"] = stop_event

    logger.info("worker_startup_completed", loaded_modules=list(module_registry.modules.keys()))


async def shutdown(ctx: dict[str, Any]) -> None:
    """Gracefully terminate background tasks and close database connections."""
    logger.info("worker_shutdown_initiated")

    stop_event: asyncio.Event | None = ctx.get("stop_event")
    if stop_event:
        stop_event.set()

    engine = ctx.get("engine")
    if engine is not None:
        await engine.dispose()

    logger.info("worker_shutdown_completed")


async def on_job_start(ctx: dict[str, Any]) -> None:
    """Record job start timestamp and bind structured logging context."""
    job_id = ctx.get("job_id", "unknown")
    job_try = ctx.get("job_try", 1)
    func_name = getattr(ctx.get("function"), "__name__", "unknown")

    ctx["_job_start_time"] = time.monotonic()
    ctx["_job_name"] = func_name

    logger.info(
        "job_started",
        job_id=job_id,
        job_name=func_name,
        job_try=job_try,
    )


async def on_job_end(ctx: dict[str, Any]) -> None:
    """Compute job latency and update Prometheus execution metrics."""
    job_id = ctx.get("job_id", "unknown")
    func_name = ctx.get("_job_name", "unknown")
    start_time = ctx.get("_job_start_time", time.monotonic())
    duration = max(0.0, time.monotonic() - start_time)

    JOB_DURATION_SECONDS.labels(job=func_name).observe(duration)
    JOB_EXECUTIONS_TOTAL.labels(job=func_name, outcome="success").inc()

    logger.info(
        "job_completed",
        job_id=job_id,
        job_name=func_name,
        duration_seconds=duration,
    )


# ---------------------------------------------------------------------------
# arq WorkerSettings Configuration
# ---------------------------------------------------------------------------


class WorkerSettings:
    """Standard settings class discovered by arq CLI or create_worker."""

    functions: list[Function | Callable[..., Any]] = worker_registry.get_functions()
    cron_jobs: list[CronJob] = worker_registry.get_cron_jobs()
    redis_settings: RedisSettings = get_redis_settings()
    on_startup = startup
    on_shutdown = shutdown
    on_job_start = on_job_start
    on_job_end = on_job_end
    max_jobs: int = 10
    job_timeout: int = 300
    max_tries: int = 3
    retry_jobs: bool = True


# ---------------------------------------------------------------------------
# Client Enqueue Helper
# ---------------------------------------------------------------------------

_pool: ArqRedis | None = None
_pool_lock = asyncio.Lock()


async def get_worker_pool(settings: Settings | None = None) -> ArqRedis:
    """Obtain or initialize the shared ArqRedis connection pool for enqueuing jobs.

    Args:
        settings: Application settings, defaults to process settings.

    Returns:
        Connected ArqRedis instance.
    """
    global _pool
    if _pool is not None:
        return _pool

    async with _pool_lock:
        if _pool is None:
            redis_settings = get_redis_settings(settings)
            _pool = await create_pool(redis_settings)
        return _pool


async def close_worker_pool() -> None:
    """Close the global ArqRedis connection pool."""
    global _pool
    async with _pool_lock:
        if _pool is not None:
            await _pool.aclose()
            _pool = None


async def enqueue_job(
    job_name: str,
    *args: Any,
    _queue_name: str | None = None,
    **kwargs: Any,
) -> Any:
    """Enqueue a job to the background worker Redis queue.

    Args:
        job_name: Registered job function name.
        args: Positional arguments for the job function.
        _queue_name: Optional custom queue name.
        kwargs: Keyword arguments for the job function.

    Returns:
        Job instance or job result handle from arq.
    """
    pool = await get_worker_pool()
    return await pool.enqueue_job(job_name, *args, _queue_name=_queue_name, **kwargs)


async def run_worker() -> None:
    """Start and run the arq worker process until interrupted."""
    worker = create_worker(cast(Any, WorkerSettings))
    await worker.async_run()


def main() -> int:
    """Entrypoint when invoked as `python -m sahayak.worker`."""
    try:
        asyncio.run(run_worker())
        return 0
    except (KeyboardInterrupt, SystemExit):
        return 0
    except Exception as exc:
        logging.getLogger(__name__).exception("Worker terminated with error: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
