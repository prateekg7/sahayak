"""Unit tests verifying performance load testing configuration and benchmark reports (T4.7)."""

from __future__ import annotations

from pathlib import Path


def test_load_test_scenarios_exist() -> None:
    """Verify Locustfile and k6 scenarios exist and define expected tasks and thresholds."""
    root = Path(__file__).resolve().parents[2]
    locust_file = root / "tests" / "load" / "locustfile.py"
    k6_file = root / "tests" / "load" / "k6_load_scenario.js"

    assert locust_file.exists(), "tests/load/locustfile.py must exist"
    assert k6_file.exists(), "tests/load/k6_load_scenario.js must exist"

    locust_content = locust_file.read_text(encoding="utf-8")
    assert "test_quiz_flow" in locust_content
    assert "test_flashcards_flow" in locust_content
    assert "test_progress_report" in locust_content
    assert "test_topic_brief_cached" in locust_content

    k6_content = k6_file.read_text(encoding="utf-8")
    assert "p(95)<800" in k6_content
    assert "rate<0.01" in k6_content


def test_perf_report_targets_and_indices() -> None:
    """Verify docs/perf/report.md documents 100 RPS results, indexing, and pool configs."""
    root = Path(__file__).resolve().parents[2]
    report_file = root / "docs" / "perf" / "report.md"
    assert report_file.exists(), "docs/perf/report.md must exist"

    content = report_file.read_text(encoding="utf-8")
    assert "100 RPS" in content
    assert "800 ms" in content or "800ms" in content
    assert "quiz_answer" in content
    assert "quiz_start" in content
    assert "Connection Pool" in content
    assert "N+1" in content
