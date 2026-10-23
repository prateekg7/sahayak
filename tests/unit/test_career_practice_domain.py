"""Unit tests for career practice domain logic (T8.3).

Google XYZ formula resume bullet improvement, daily questions, and answer evaluation.
"""

from __future__ import annotations

import pytest

from sahayak.core.errors import InvalidInputError
from sahayak.modules.career.domain.practice import (
    CURATED_DAILY_QUESTIONS,
    evaluate_daily_answer,
    get_next_daily_question,
    improve_resume_bullet,
)


def test_improve_resume_bullet_xyz_formula() -> None:
    bullet = "Built an authentication service that reduced login latency"
    res = improve_resume_bullet(bullet)

    assert "action" in res
    assert "metrics" in res
    assert "improved_variations" in res
    assert len(res["improved_variations"]) >= 2
    assert res["xyz_formula"] == "Accomplished [X], as measured by [Y], by doing [Z]"
    assert res["action"] == "Built"

    # Spoken summary compliance
    spoken = res["spoken_explanation"]
    assert len(spoken) <= 300
    assert "*" not in spoken
    assert "#" not in spoken
    assert "`" not in spoken


def test_improve_resume_bullet_empty_raises() -> None:
    with pytest.raises(InvalidInputError):
        improve_resume_bullet("   ")


def test_curated_daily_questions_validity() -> None:
    assert len(CURATED_DAILY_QUESTIONS) >= 8
    keys = set()
    for q in CURATED_DAILY_QUESTIONS:
        assert q.key not in keys, f"Duplicate key {q.key}"
        keys.add(q.key)
        assert len(q.topic) > 0
        assert len(q.stem) > 0
        assert len(q.sample_answer) > 0
        assert len(q.keywords) >= 2


def test_daily_question_rotation_unanswered() -> None:
    answered = [CURATED_DAILY_QUESTIONS[0].key]
    next_q = get_next_daily_question(answered)
    assert next_q.key != CURATED_DAILY_QUESTIONS[0].key
    assert next_q.key == CURATED_DAILY_QUESTIONS[1].key


def test_daily_question_rotation_all_answered_wraps_around() -> None:
    all_keys = [q.key for q in CURATED_DAILY_QUESTIONS]
    next_q = get_next_daily_question(all_keys)
    assert next_q.key == CURATED_DAILY_QUESTIONS[0].key


def test_evaluate_daily_answer_accurate() -> None:
    q = CURATED_DAILY_QUESTIONS[0]  # star_method_intro
    answer = (
        "The STAR method stands for situation, task, action, and result "
        "to structure interview responses."
    )
    is_correct, feedback = evaluate_daily_answer(q, answer)

    assert is_correct is True
    assert len(feedback) <= 300
    assert "*" not in feedback
    assert "#" not in feedback
    assert "Great job" in feedback or "Spot on" in feedback


def test_evaluate_daily_answer_weak() -> None:
    q = CURATED_DAILY_QUESTIONS[0]
    answer = "I don't really know, maybe it's about astronomy."
    is_correct, feedback = evaluate_daily_answer(q, answer)

    assert is_correct is False
    assert len(feedback) <= 300
    assert "*" not in feedback
    assert "Good effort" in feedback or "Good try" in feedback
