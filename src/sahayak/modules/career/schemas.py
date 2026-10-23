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


ApplicationAction = Literal["add", "update_status", "list", "due_followups", "delete"]


class ApplicationRequest(BaseModel):
    """Input payload for application_tracker tool (T8.2)."""

    action: ApplicationAction = Field(
        ...,
        description="Action: 'add', 'update_status', 'list', 'due_followups', or 'delete'",
    )
    company: str | None = Field(
        default=None,
        description="Company name, e.g. 'Google' or 'Stripe'",
    )
    role: str | None = Field(
        default=None,
        description="Job role or title, e.g. 'Software Engineer'",
    )
    status: str | None = Field(
        default=None,
        description="Optional status filter or application status (e.g. 'applied', 'interviewing')",
    )
    follow_up_at: str | None = Field(
        default=None,
        description="Follow-up deadline, e.g. 'in 3 days', 'tomorrow', 'next week', or ISO date",
    )
    notes: str | None = Field(
        default=None,
        description="Optional notes regarding the application or interview process",
    )
    application_id: str | None = Field(
        default=None,
        description="UUID of the application (required for 'update_status' and 'delete')",
    )
    limit: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum number of applications to list",
    )


CareerPracticeAction = Literal["improve_bullet", "daily_question", "check_answer"]


class CareerPracticeRequest(BaseModel):
    """Input payload for career_practice tool (T8.3)."""

    action: CareerPracticeAction = Field(
        ...,
        description="Action: 'improve_bullet', 'daily_question', or 'check_answer'",
    )
    bullet: str | None = Field(
        default=None,
        description="Resume bullet point to polish using Google XYZ formula (for 'improve_bullet')",
    )
    question_key: str | None = Field(
        default=None,
        description="Key of the daily question being answered (for 'check_answer')",
    )
    answer: str | None = Field(
        default=None,
        description="Candidate's answer to the daily question (for 'check_answer')",
    )
