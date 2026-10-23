"""Unit tests for Academics models, enums, and validations (T3.1)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sahayak.core.module import Module
from sahayak.modules.academics.models import (
    Card,
    Deck,
    DifficultyLevel,
    PlanTask,
    Question,
    QuestionStatus,
    Quiz,
    QuizQuestion,
    QuizStatus,
    StudyPlan,
    Topic,
)
from sahayak.modules.academics.module import module as academics_module


def test_academics_module_satisfies_protocol() -> None:
    """AcademicsModule satisfies the Module protocol contract."""
    assert isinstance(academics_module, Module)
    assert academics_module.name == "academics"
    assert academics_module.version == "0.1.0"
    assert academics_module.health().healthy is True
    assert academics_module.migrations_path() is not None


def test_difficulty_level_enum_values() -> None:
    assert DifficultyLevel.EASY.value == "easy"
    assert DifficultyLevel.MEDIUM.value == "medium"
    assert DifficultyLevel.HARD.value == "hard"


def test_question_status_enum_values() -> None:
    assert QuestionStatus.APPROVED.value == "approved"
    assert QuestionStatus.FLAGGED.value == "flagged"
    assert QuestionStatus.QUARANTINED.value == "quarantined"


def test_quiz_status_enum_values() -> None:
    assert QuizStatus.IN_PROGRESS.value == "in_progress"
    assert QuizStatus.COMPLETED.value == "completed"
    assert QuizStatus.ABANDONED.value == "abandoned"
    assert QuizStatus.EXPIRED.value == "expired"


def test_topic_model_initialization() -> None:
    topic_id = uuid.uuid4()
    topic = Topic(
        id=topic_id,
        topic_key="photosynthesis",
        display_name="Photosynthesis",
    )
    assert topic.id == topic_id
    assert topic.topic_key == "photosynthesis"
    assert topic.display_name == "Photosynthesis"


def test_question_model_initialization() -> None:
    q_id = uuid.uuid4()
    topic_id = uuid.uuid4()
    options = {"A": "60 seconds", "B": "100 seconds", "C": "10 seconds", "D": "120 seconds"}

    question = Question(
        id=q_id,
        topic_id=topic_id,
        difficulty=DifficultyLevel.EASY,
        stem="How many seconds are in a minute?",
        options=options,
        correct_key="A",
        explanation="One minute equals exactly sixty seconds.",
        content_hash="hash-123456",
        prompt_version="v1",
        model="gemini-2.5-flash",
    )
    assert question.id == q_id
    assert question.topic_id == topic_id
    assert question.correct_key == "A"
    assert question.correct_key in question.options
    assert question.status == QuestionStatus.APPROVED
    assert question.flag_count == 0


def test_quiz_and_quiz_question_initialization() -> None:
    quiz_id = uuid.uuid4()
    topic_id = uuid.uuid4()
    user_id = uuid.uuid4()
    q_id = uuid.uuid4()

    quiz = Quiz(
        id=quiz_id,
        user_id=user_id,
        topic_id=topic_id,
        difficulty=DifficultyLevel.MEDIUM,
        total=5,
        expires_at=datetime.now(UTC),
    )
    assert quiz.id == quiz_id
    assert quiz.user_id == user_id
    assert quiz.status == QuizStatus.IN_PROGRESS
    assert quiz.score_correct == 0

    quiz_question = QuizQuestion(
        quiz_id=quiz_id,
        position=1,
        question_id=q_id,
        selected_key="B",
        is_correct=True,
    )
    assert quiz_question.quiz_id == quiz_id
    assert quiz_question.position == 1
    assert quiz_question.is_correct is True


def test_card_deck_and_planner_initialization() -> None:
    user_id = uuid.uuid4()
    deck_id = uuid.uuid4()

    deck = Deck(id=deck_id, user_id=user_id, name="Biology")
    card = Card(
        deck_id=deck_id,
        user_id=user_id,
        front="What is ATP?",
        back="Adenosine triphosphate",
    )
    assert deck.name == "Biology"
    assert card.ease == 2.5
    assert card.repetitions == 0

    plan_id = uuid.uuid4()
    plan = StudyPlan(
        id=plan_id,
        user_id=user_id,
        goal="AP Biology Exam",
        exam_date=datetime.now(UTC).date(),
    )
    task = PlanTask(
        plan_id=plan_id,
        date=datetime.now(UTC).date(),
        topic="Cellular Respiration",
        minutes=45,
    )
    assert plan.goal == "AP Biology Exam"
    assert task.minutes == 45
    assert task.done_at is None
