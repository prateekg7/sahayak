"""Pydantic request and response schemas for career module (T8.1)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

InterviewAction = Literal["start", "answer", "finish", "history"]


class InterviewRequest(BaseModel):
    """Input payload for interview_practice tool."""

    action: InterviewAction = Field(
        ...,
        description="Interview action: 'start', 'answer', 'finish', or 'history'",
    )
    role: str | None = Field(
        default="Software Engineer",
        description="Target role for mock interview (e.g. 'Software Engineer')",
    )
    level: str | None = Field(
        default="mid",
        description="Target seniority level: 'junior', 'mid', or 'senior'",
    )
    total_questions: int = Field(
        default=5,
        ge=1,
        le=5,
        description="Total number of questions for the session (between 1 and 5)",
    )
    session_id: str | None = Field(
        default=None,
        description="UUID of the active interview session (required for 'answer' and 'finish')",
    )
    answer: str | None = Field(
        default=None,
        description="Candidate's spoken answer to the current question (required for 'answer')",
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum number of historical sessions to return for 'history'",
    )


class TurnScorePayload(BaseModel):
    """Rubric scoring details for a turn."""

    question_index: int
    question_text: str
    clarity_score: int
    relevance_score: int
    depth_score: int
    average_score: float
    feedback_tips: list[str]
    feedback_spoken: str


class InterviewSessionPayload(BaseModel):
    """Interview session metadata payload."""

    session_id: str
    role: str
    level: str
    status: str
    current_question_index: int
    total_questions: int
    current_question: str | None = None
    created_at: str | None = None
    finished_at: str | None = None
    turns: list[dict[str, Any]] = Field(default_factory=list)
