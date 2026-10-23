"""Prometheus metrics definitions and exposition helpers."""

from __future__ import annotations

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)

# Use dedicated registry to prevent collisions during tests
registry = CollectorRegistry(auto_describe=True)

# 1. MCP Tool metrics (PRD §10, §24.4)
TOOL_CALLS_TOTAL = Counter(
    "sahayak_tool_calls_total",
    "Total number of MCP tool invocations.",
    ["tool", "module", "outcome"],
    registry=registry,
)

TOOL_DURATION_SECONDS = Histogram(
    "sahayak_tool_duration_seconds",
    "Duration of MCP tool executions in seconds.",
    ["tool", "module"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.45, 0.5, 1.0, 2.5),
    registry=registry,
)

# 2. Cache metrics
CACHE_HITS_TOTAL = Counter(
    "sahayak_cache_hits_total",
    "Total number of cache read hits.",
    ["cache_name"],
    registry=registry,
)

CACHE_MISSES_TOTAL = Counter(
    "sahayak_cache_misses_total",
    "Total number of cache read misses.",
    ["cache_name"],
    registry=registry,
)

# 3. LLM metrics (registered early per PRD §10)
LLM_REQUESTS_TOTAL = Counter(
    "sahayak_llm_requests_total",
    "Total number of outbound LLM requests.",
    ["provider", "model", "outcome"],
    registry=registry,
)

LLM_DURATION_SECONDS = Histogram(
    "sahayak_llm_duration_seconds",
    "Outbound LLM call duration in seconds.",
    ["provider", "model"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=registry,
)

LLM_TOKENS_TOTAL = Counter(
    "sahayak_llm_tokens_total",
    "Total token count consumed from LLM providers.",
    ["provider", "model", "token_type"],
    registry=registry,
)

# 4. Background worker metrics (PRD §10, T2.5)
JOB_EXECUTIONS_TOTAL = Counter(
    "sahayak_job_executions_total",
    "Total background worker job executions.",
    ["job", "outcome"],
    registry=registry,
)

JOB_DURATION_SECONDS = Histogram(
    "sahayak_job_duration_seconds",
    "Duration of background job executions in seconds.",
    ["job"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
    registry=registry,
)

# 5. Question verification metrics (PRD §11.2, T3.4)
QUESTION_VERIFICATION_ATTEMPTS_TOTAL = Counter(
    "sahayak_question_verification_attempts_total",
    "Total number of generated question verification attempts.",
    ["topic", "outcome"],
    registry=registry,
)

QUESTION_VERIFICATION_REJECTIONS_TOTAL = Counter(
    "sahayak_question_verification_rejections_total",
    "Total number of generated question verification rejections.",
    ["topic", "reason"],
    registry=registry,
)


def render_metrics() -> tuple[bytes, str]:
    """Serialize all registered Prometheus metrics to the standard text format.

    Returns:
        A tuple of (encoded_metrics_bytes, content_type_header_value).
    """
    return generate_latest(registry), CONTENT_TYPE_LATEST
