"""Pydantic schemas for the academics module tools and API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class QuizStartRequest(BaseModel):
    """Input payload for quiz_start tool."""

    topic: str | None = Field(
        default=None,
        max_length=120,
        description="Academic topic or subject to be quizzed on (e.g. 'Photosynthesis').",
    )
    source: Literal["topic", "weak_topics", "due_review"] = Field(
        default="topic",
        description="Source of questions: topic name, user's weakest topics, or due reviews.",
    )
    difficulty: Literal["easy", "medium", "hard"] = Field(
        default="medium",
        description="Target question difficulty level.",
    )
    num_questions: int = Field(
        default=5,
        ge=3,
        le=10,
        description="Total number of questions in the quiz (between 3 and 10).",
    )
    request_id: str | None = Field(
        default=None,
        description="Optional client request ID for idempotent execution.",
    )


class QuizOption(BaseModel):
    """Multiple choice question option presentation."""

    key: str = Field(description="Option letter ('A', 'B', 'C', or 'D').")
    text: str = Field(description="Display text of the option.")


class QuizStartResponseData(BaseModel):
    """Structured data payload returned by quiz_start."""

    quiz_id: str = Field(description="Opaque handle for the active quiz session.")
    number: int = Field(default=1, description="Current question index (1-indexed).")
    total: int = Field(description="Total count of questions in this quiz session.")
    topic: str = Field(description="Normalized display name of the quiz topic.")
    difficulty: str = Field(description="Difficulty level of the quiz.")
    question: str = Field(description="Stem of the first question.")
    options: list[QuizOption] = Field(description="List of multiple-choice options.")


class QuizAnswerRequest(BaseModel):
    """Input payload for quiz_answer tool."""

    quiz_id: str = Field(description="ID of the active quiz session.")
    answer: str = Field(
        min_length=1,
        max_length=200,
        description="User's spoken or typed answer (e.g. 'option B', 'photosynthesis').",
    )
    request_id: str | None = Field(
        default=None,
        description="Optional client request ID for idempotent execution.",
    )


class QuizScoreData(BaseModel):
    """Score summary counters."""

    correct: int = Field(description="Number of correct answers so far.")
    answered: int = Field(description="Total questions answered so far.")
    total: int = Field(description="Total questions in the quiz.")


class NextQuestionData(BaseModel):
    """Details for the subsequent question in the quiz."""

    number: int = Field(description="Question number (1-indexed).")
    question: str = Field(description="Question stem.")
    options: list[QuizOption] = Field(description="List of multiple-choice options.")


class QuizAnswerResponseData(BaseModel):
    """Structured data payload returned by quiz_answer."""

    correct: bool = Field(description="Whether the submitted answer was correct.")
    correct_key: str = Field(description="The correct option key ('A', 'B', 'C', or 'D').")
    explanation: str = Field(description="Brief explanation of the correct answer.")
    score: QuizScoreData = Field(description="Progress and score counters.")
    next: NextQuestionData | None = Field(
        default=None,
        description="Details for the next question, or None if quiz is finished.",
    )
    finished: bool = Field(description="Whether all questions have been answered.")
    summary: str | None = Field(
        default=None,
        description="Final completion summary if finished.",
    )
