"""Unit tests for monitoring dashboards, alarms as code, and SLO definitions (T4.4)."""

from __future__ import annotations

import json
from pathlib import Path


def test_grafana_dashboard_json_structure() -> None:
    """Verify Grafana dashboard JSON exists, parses cleanly, and contains required panels."""
    root = Path(__file__).resolve().parents[2]
    dashboard_file = root / "infra" / "monitoring" / "dashboards" / "sahayak_overview.json"
    assert dashboard_file.exists(), "Grafana dashboard sahayak_overview.json must exist"

    data = json.loads(dashboard_file.read_text(encoding="utf-8"))
    assert "panels" in data
    panels = data["panels"]
    assert len(panels) >= 5, "Dashboard must have at least 5 monitoring panels"

    panel_titles = [p.get("title", "") for p in panels]
    assert any("Availability" in t for t in panel_titles)
    assert any("Latency" in t for t in panel_titles)
    assert any("Error Rate" in t for t in panel_titles)
    assert any("LLM" in t for t in panel_titles)
    assert any("Worker" in t for t in panel_titles)

    # Check that Prometheus metric names referenced match codebase
    all_exprs = " ".join(target.get("expr", "") for p in panels for target in p.get("targets", []))
    assert "sahayak_tool_calls_total" in all_exprs
    assert "sahayak_tool_duration_seconds" in all_exprs
    assert "sahayak_llm_requests_total" in all_exprs
    assert "sahayak_job_executions_total" in all_exprs


def test_cloudwatch_alarms_tf_configuration() -> None:
    """Verify CloudWatch alarms HCL contains all required alert thresholds."""
    root = Path(__file__).resolve().parents[2]
    alarms_tf = root / "infra" / "monitoring" / "cloudwatch_alarms.tf"
    assert alarms_tf.exists(), "cloudwatch_alarms.tf must exist"

    content = alarms_tf.read_text(encoding="utf-8")
    assert "high_error_rate" in content
    assert "high_latency_p95" in content
    assert "rds_high_connections" in content
    assert "redis_high_memory" in content
    assert "llm_fallback_spike" in content
    assert "llm_budget_exhaustion" in content
    assert "aws_sns_topic" in content


def test_slo_documentation_targets() -> None:
    """Verify SLO document specifies 99.9% availability and voice latency thresholds."""
    root = Path(__file__).resolve().parents[2]
    slo_doc = root / "infra" / "monitoring" / "slo.md"
    assert slo_doc.exists(), "slo.md must exist"

    content = slo_doc.read_text(encoding="utf-8")
    assert "99.9%" in content
    assert "800" in content  # 800ms deterministic threshold
    assert "3500" in content  # 3500ms LLM threshold
