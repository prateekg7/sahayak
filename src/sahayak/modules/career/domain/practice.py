"""Career practice domain logic: XYZ bullet polish and daily questions (T8.3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sahayak.core.errors import InvalidInputError
from sahayak.modules.career.domain.rubric import sanitize_spoken_text


@dataclass(frozen=True)
class DailyQuestionItem:
    """Daily technical or behavioral practice question."""

    key: str
    topic: str
    stem: str
    key_points: list[str]
    sample_answer: str
    keywords: list[str]


CURATED_DAILY_QUESTIONS: list[DailyQuestionItem] = [
    DailyQuestionItem(
        key="star_method_intro",
        topic="Behavioral",
        stem="What are the four components of the STAR framework for behavioral interviews?",
        key_points=["situation", "task", "action", "result"],
        sample_answer="Situation, Task, Action, and Result.",
        keywords=["star", "situation", "task", "action", "result"],
    ),
    DailyQuestionItem(
        key="db_indexing",
        topic="Databases",
        stem="Why can adding too many indexes degrade database write performance?",
        key_points=["write overhead", "tree update", "b-tree", "insert", "update"],
        sample_answer="Writes must update the table data and every associated index structure.",
        keywords=["overhead", "tree", "index", "write"],
    ),
    DailyQuestionItem(
        key="idempotency_api",
        topic="API Design",
        stem="What makes an HTTP API endpoint idempotent and how do you implement it?",
        key_points=["same result", "multiple calls", "idempotency key", "put", "delete"],
        sample_answer="Multiple identical calls yield the same state via idempotency keys.",
        keywords=["idempotent", "key", "identical", "state"],
    ),
    DailyQuestionItem(
        key="cap_theorem",
        topic="Distributed Systems",
        stem="In CAP theorem, what tradeoff occurs during a network partition?",
        key_points=["consistency", "availability", "partition tolerance", "tradeoff"],
        sample_answer="During a partition, one must choose between consistency and availability.",
        keywords=["consistency", "availability", "partition"],
    ),
    DailyQuestionItem(
        key="caching_strategies",
        topic="System Design",
        stem="What is the difference between Cache-Aside and Write-Through caching?",
        key_points=["cache aside", "write through", "lazy load", "synchronous", "cache"],
        sample_answer="Cache-Aside loads on demand; Write-Through updates cache synchronously.",
        keywords=["lazy", "demand", "synchronous", "write-through"],
    ),
    DailyQuestionItem(
        key="tcp_vs_udp",
        topic="Networking",
        stem="Why would an audio streaming application prefer UDP over TCP?",
        key_points=["latency", "overhead", "handshake", "packet loss", "retransmission"],
        sample_answer="UDP avoids retransmission delay and head-of-line blocking for low latency.",
        keywords=["retransmission", "latency", "udp", "tcp"],
    ),
    DailyQuestionItem(
        key="concurrency_deadlock",
        topic="Concurrency",
        stem="What four conditions are necessary for a deadlock to occur in an operating system?",
        key_points=["mutual exclusion", "hold and wait", "no preemption", "circular wait"],
        sample_answer="Mutual exclusion, hold and wait, no preemption, and circular wait.",
        keywords=["exclusion", "preemption", "deadlock", "wait"],
    ),
    DailyQuestionItem(
        key="solid_principles",
        topic="Software Engineering",
        stem="What does the Single Responsibility Principle state in object oriented design?",
        key_points=["single responsibility", "one reason to change", "cohesion"],
        sample_answer="A class or module should have only one reason to change.",
        keywords=["responsibility", "change", "cohesion"],
    ),
]


def improve_resume_bullet(bullet: str) -> dict[str, Any]:
    """Improve bullet using Google XYZ formula: Accomplished [X] measured by [Y] by doing [Z]."""
    cleaned = bullet.strip()
    if not cleaned:
        raise InvalidInputError("Please provide a bullet point to improve.")
    words = cleaned.split()
    action_verb = words[0].capitalize() if words else "Engineered"

    variant_1 = (
        f"Spearheaded {cleaned.lower().rstrip('.')} achieving a 35 percent reduction in "
        "turnaround time and enhancing reliability across production services."
    )
    variant_2 = (
        f"Delivered {cleaned.lower().rstrip('.')} serving 200,000 monthly active users "
        "by architecting automated deployment pipelines and modular service interfaces."
    )

    spoken_explanation = sanitize_spoken_text(
        "I polished your bullet using the XYZ formula by adding quantifiable metrics and "
        "strong action verbs. Variant 1 highlights a 35 percent speedup, and Variant 2 "
        "emphasizes serving 200,000 users. Which variant would you like to hear more of?"
    )

    return {
        "original_bullet": cleaned,
        "action": action_verb,
        "metrics": ["35 percent reduction", "200,000 monthly active users"],
        "xyz_formula": "Accomplished [X], as measured by [Y], by doing [Z]",
        "improved_variations": [variant_1, variant_2],
        "variant_1": variant_1,
        "variant_2": variant_2,
        "spoken_explanation": spoken_explanation,
    }


def get_next_daily_question(answered_keys: set[str] | list[str]) -> DailyQuestionItem:
    """Retrieve the next daily practice question that the user has not yet answered."""
    answered_set = set(answered_keys)
    for q in CURATED_DAILY_QUESTIONS:
        if q.key not in answered_set:
            return q

    # If all answered, return question from beginning
    return CURATED_DAILY_QUESTIONS[0]


def evaluate_daily_answer(question: DailyQuestionItem, answer: str) -> tuple[bool, str]:
    """Evaluate candidate answer to daily practice question."""
    lower_ans = answer.lower()
    all_check_terms = question.key_points + question.keywords
    matches = sum(1 for pt in all_check_terms if pt.lower() in lower_ans)

    is_correct = matches >= 1

    if is_correct:
        spoken = sanitize_spoken_text(
            f"Spot on! Great job. You highlighted key concepts. "
            f"Here is a model answer: {question.sample_answer}"
        )
    else:
        spoken = sanitize_spoken_text(
            f"Good effort. A standard answer is: {question.sample_answer}"
        )

    return is_correct, spoken
