"""Unit tests for career interview domain logic and rubric evaluation (T8.1)."""

from __future__ import annotations

from sahayak.modules.career.domain.rubric import (
    RubricScore,
    get_questions_for_role,
    parse_rubric_evaluation,
    sanitize_spoken_text,
)


def test_get_questions_for_role_curated_and_fallback() -> None:
    # Known role Software Engineer junior
    swe_jr = get_questions_for_role("Software Engineer", "junior", count=3)
    assert len(swe_jr) == 3
    assert any("bug" in q.lower() or "programming" in q.lower() for q in swe_jr)

    # Known role Product Manager mid
    pm_mid = get_questions_for_role("Product Manager", "mid", count=5)
    assert len(pm_mid) == 5
    assert any(
        "roadmap" in q.lower() or "stakeholder" in q.lower() or "feature" in q.lower()
        for q in pm_mid
    )

    # Unknown role falls back gracefully to general questions
    custom_role = get_questions_for_role("Quantum Physicist", "senior", count=4)
    assert len(custom_role) == 4
    assert all(len(q) > 10 for q in custom_role)


def test_sanitize_spoken_text_strips_markdown_and_quotes() -> None:
    raw = 'Here is your **great** answer with *markdown*, "double quotes", and `code snippet`! 🚀'
    cleaned = sanitize_spoken_text(raw)
    assert "*" not in cleaned
    assert "`" not in cleaned
    assert '"' not in cleaned
    assert "🚀" not in cleaned
    assert "Here is your great answer with markdown" in cleaned


def test_parse_rubric_evaluation_valid_json() -> None:
    raw_json = """
    {
        "clarity_score": 4,
        "relevance_score": 5,
        "depth_score": 4,
        "feedback_tips": ["Structure using the STAR framework.", "Add more quantitative data."],
        "feedback_spoken": "Strong answer that directly addressed the problem."
    }
    """
    res = parse_rubric_evaluation(raw_json, "What is your experience?", "I built an API.")
    assert isinstance(res, RubricScore)
    assert res.clarity_score == 4
    assert res.relevance_score == 5
    assert res.depth_score == 4
    assert res.average_score == 4.3
    assert len(res.feedback_tips) == 2
    assert "Strong answer" in res.feedback_spoken


def test_parse_rubric_evaluation_markdown_fenced_json() -> None:
    raw_markdown = """```json
    {
        "clarity_score": 5,
        "relevance_score": 4,
        "depth_score": 3,
        "feedback_tips": ["Mention the team size."],
        "feedback_spoken": "Clear and structured response."
    }
    ```"""
    res = parse_rubric_evaluation(raw_markdown, "Tell me about a bug", "Fixed a memory leak.")
    assert res.clarity_score == 5
    assert res.depth_score == 3
    assert res.average_score == 4.0
    assert "Clear and structured" in res.feedback_spoken


def test_parse_rubric_evaluation_malformed_fallback() -> None:
    raw_broken = "I am an AI and here is my free-form analysis without JSON..."
    res = parse_rubric_evaluation(
        raw_broken, "Tell me about a bug", "I solved a concurrency bug with a lock."
    )
    assert isinstance(res, RubricScore)
    assert 1 <= res.clarity_score <= 5
    assert 1 <= res.relevance_score <= 5
    assert 1 <= res.depth_score <= 5
    assert len(res.feedback_tips) >= 1
    assert "Your answer scored" in res.feedback_spoken
