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


FlashcardAction = Literal["add", "review_next", "grade", "list_due"]
FlashcardRating = Literal["again", "hard", "good", "easy"]


class FlashcardsRequest(BaseModel):
    """Input payload for flashcards tool."""

    action: FlashcardAction = Field(
        description="Action to perform: 'add', 'review_next', 'grade', or 'list_due'."
    )
    front: str | None = Field(
        default=None,
        max_length=2000,
        description="Question or prompt on the front of the flashcard (required for 'add').",
    )
    back: str | None = Field(
        default=None,
        max_length=2000,
        description="Answer or explanation on the back of the flashcard (required for 'add').",
    )
    deck: str | None = Field(
        default=None,
        max_length=120,
        description="Optional deck name to group the flashcard into.",
    )
    card_id: str | None = Field(
        default=None,
        description="Identifier of the card being graded (required for 'grade').",
    )
    rating: FlashcardRating | None = Field(
        default=None,
        description="Review performance rating: 'again', 'hard', 'good', or 'easy'.",
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum count of due cards to return for 'list_due'.",
    )
    request_id: str | None = Field(
        default=None,
        description="Optional client request ID for idempotent execution.",
    )


class FlashcardCardData(BaseModel):
    """Data representation of a single flashcard."""

    card_id: str = Field(description="Unique identifier of the flashcard.")
    front: str = Field(description="Front prompt or question.")
    back: str | None = Field(default=None, description="Back answer or explanation.")
    deck: str | None = Field(default=None, description="Deck name.")
    ease: float | None = Field(default=None, description="SM-2 ease factor.")
    interval_days: int | None = Field(
        default=None, description="Interval in days until next review."
    )
    repetitions: int | None = Field(default=None, description="Number of successful reviews.")
    due_at: str | None = Field(default=None, description="ISO timestamp when card is due.")


class FlashcardsResponseData(BaseModel):
    """Structured data payload returned by the flashcards tool."""

    action: str = Field(description="The action executed.")
    card: FlashcardCardData | None = Field(
        default=None,
        description="Card details for 'add', 'review_next', or 'grade'.",
    )
    total_due: int | None = Field(
        default=None,
        description="Total count of due cards for 'list_due' or 'review_next'.",
    )
    cards: list[FlashcardCardData] | None = Field(
        default=None,
        description="List of due cards for 'list_due'.",
    )
    rating: str | None = Field(
        default=None,
        description="Submitted rating for 'grade'.",
    )
    next_review_days: int | None = Field(
        default=None,
        description="Days until next review after grading.",
    )


StudyPlanAction = Literal["create", "today", "update", "list"]


class StudyPlanRequest(BaseModel):
    """Input payload for study_plan tool."""

    action: StudyPlanAction = Field(
        description="Action to perform: 'create', 'today', 'update', or 'list'."
    )
    goal: str | None = Field(
        default=None,
        max_length=256,
        description="Subject or exam goal (required for 'create', e.g., 'chemistry exam').",
    )
    exam_date: str | None = Field(
        default=None,
        description=(
            "Exam date in ISO format (YYYY-MM-DD) or relative phrase "
            "(e.g., '2026-11-15', 'in 2 weeks'). Required for 'create'."
        ),
    )
    topics: list[str] | None = Field(
        default=None,
        description="List of topics to cover. If omitted, key topics are automatically generated.",
    )
    hours_per_day: float = Field(
        default=1.0,
        ge=0.25,
        le=12.0,
        description="Allocated study hours per day (default 1.0).",
    )
    timezone: str = Field(
        default="UTC",
        description="User timezone name (e.g., 'America/New_York', 'Asia/Kolkata').",
    )
    plan_id: str | None = Field(
        default=None,
        description="Specific plan identifier (optional for 'today', 'update').",
    )
    task_id: str | None = Field(
        default=None,
        description="Task identifier to mark as completed under 'update'.",
    )
    mark_done: bool | None = Field(
        default=None,
        description="Whether to mark the specified task as done under 'update'.",
    )
    replan: bool = Field(
        default=False,
        description="Whether to replan remaining days and tasks under 'update'.",
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum count of plans to return for 'list'.",
    )
    request_id: str | None = Field(
        default=None,
        description="Optional client request ID for idempotent execution.",
    )


class PlanTaskData(BaseModel):
    """Data representation of a single planned daily study task."""

    task_id: str = Field(description="Unique task identifier.")
    date: str = Field(description="ISO date when task is scheduled.")
    topic: str = Field(description="Topic or review title.")
    minutes: int = Field(description="Duration in minutes.")
    done: bool = Field(description="Whether the task has been marked completed.")
    done_at: str | None = Field(
        default=None,
        description="ISO timestamp when marked done.",
    )


class StudyPlanSummaryData(BaseModel):
    """Summary overview of a study plan."""

    plan_id: str = Field(description="Unique plan identifier.")
    goal: str = Field(description="Study goal or exam target.")
    exam_date: str = Field(description="Target exam date.")
    total_tasks: int = Field(description="Total tasks scheduled.")
    completed_tasks: int = Field(description="Tasks marked done.")
    created_at: str = Field(description="ISO creation timestamp.")


class StudyPlanResponseData(BaseModel):
    """Structured data payload returned by the study_plan tool."""

    action: str = Field(description="The action executed.")
    plan_id: str | None = Field(
        default=None,
        description="Identifier of the referenced plan.",
    )
    goal: str | None = Field(
        default=None,
        description="Plan goal or subject name.",
    )
    exam_date: str | None = Field(
        default=None,
        description="Exam date in ISO format.",
    )
    today_tasks: list[PlanTaskData] | None = Field(
        default=None,
        description="Tasks scheduled for today.",
    )
    tasks: list[PlanTaskData] | None = Field(
        default=None,
        description="All plan tasks or replanned tasks.",
    )
    plans: list[StudyPlanSummaryData] | None = Field(
        default=None,
        description="List of user plans for 'list' action.",
    )
    total_days: int | None = Field(
        default=None,
        description="Total days in schedule.",
    )
    daily_minutes: int | None = Field(
        default=None,
        description="Target study minutes per day.",
    )
    is_feasible: bool | None = Field(
        default=None,
        description="Whether all topics could be scheduled within capacity.",
    )
    warning_message: str | None = Field(
        default=None,
        description="Feasibility warning if time is constrained.",
    )
    updated_task: PlanTaskData | None = Field(
        default=None,
        description="Task details updated during 'update' action.",
    )


# ---------------------------------------------------------------------------
# Progress Report Tool Schemas (T3.13)
# ---------------------------------------------------------------------------

ProgressScope = Literal["summary", "weak_topics", "streak", "weekly"]


class ProgressReportRequest(BaseModel):
    """Input payload for progress_report tool."""

    scope: ProgressScope = Field(
        default="summary",
        description=(
            "Aspect of progress to inspect: 'summary', 'weak_topics', 'streak', or 'weekly'."
        ),
    )
    timezone: str = Field(
        default="UTC",
        description=(
            "User timezone name (e.g. 'America/New_York', 'Asia/Kolkata') "
            "for calendar day resolution."
        ),
    )


class WeakTopicData(BaseModel):
    """Performance summary for a weak topic."""

    topic: str = Field(description="Display name of the academic topic.")
    attempts: int = Field(description="Total questions attempted.")
    correct: int = Field(description="Questions answered correctly.")
    accuracy_pct: float = Field(description="Percentage accuracy.")


class StreakData(BaseModel):
    """Study streak information."""

    current_streak: int = Field(description="Consecutive days studied ending today or yesterday.")
    longest_streak: int = Field(description="Maximum consecutive days studied historically.")
    studied_today: bool = Field(description="Whether user has recorded study activity today.")
    last_active_date: str | None = Field(
        default=None,
        description="Last date studied in ISO format.",
    )


class WeeklySummaryData(BaseModel):
    """7-day activity metrics."""

    active_days: int = Field(description="Days active in the past 7 days (0-7).")
    quizzes_completed: int = Field(description="Total quizzes finished in the past 7 days.")
    questions_answered: int = Field(description="Total questions answered in the past 7 days.")
    correct_count: int = Field(description="Total correct answers in the past 7 days.")
    accuracy_pct: float = Field(description="Overall accuracy percentage in the past 7 days.")
    cards_reviewed: int = Field(description="Total flashcard reviews in the past 7 days.")


class ProgressReportResponseData(BaseModel):
    """Structured data returned by progress_report tool."""

    scope: ProgressScope = Field(description="Requested report scope.")
    streak: StreakData = Field(description="Streak information.")
    total_quizzes: int | None = Field(default=None, description="All-time completed quizzes.")
    total_questions: int | None = Field(default=None, description="All-time questions answered.")
    total_correct: int | None = Field(default=None, description="All-time correct answers.")
    accuracy_pct: float | None = Field(default=None, description="All-time accuracy percentage.")
    weak_topics: list[WeakTopicData] | None = Field(
        default=None, description="Ranked list of weak topics needing reinforcement."
    )
    weekly: WeeklySummaryData | None = Field(
        default=None, description="7-day activity metrics for 'weekly' scope."
    )


# ---------------------------------------------------------------------------
# Topic Brief Schemas (T3.14)
# ---------------------------------------------------------------------------

BriefLength = Literal["short", "medium"]


class TopicBriefRequest(BaseModel):
    """Input parameters for topic_brief tool."""

    topic: str = Field(
        min_length=1,
        max_length=128,
        description="Academic topic or subject to summarize.",
    )
    length: BriefLength = Field(
        default="short",
        description="Desired summary length: 'short' (1-2 sentences) or 'medium' (3-4 sentences).",
    )


class TopicBriefSource(BaseModel):
    """Grounding source reference."""

    title: str = Field(description="Title of the source reference.")
    url: str = Field(description="Canonical URL to the reference document.")


class TopicBriefResponseData(BaseModel):
    """Structured response payload for topic_brief tool."""

    topic: str = Field(description="Canonical topic key.")
    display_name: str = Field(description="Display title of the topic.")
    brief: str = Field(description="Verified spoken summary text.")
    length: BriefLength = Field(description="Length style of the brief.")
    sources: list[TopicBriefSource] = Field(
        default_factory=list,
        description="Grounding citations used to produce the brief.",
    )


class RawTopicBriefOutput(BaseModel):
    """Structured LLM output container for topic brief generation."""

    brief: str = Field(description="Spoken summary of the topic grounded in reference text.")
