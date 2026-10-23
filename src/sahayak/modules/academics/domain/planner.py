"""Deterministic study plan scheduling domain logic (T3.11).

Provides pure, deterministic day-by-day exam preparation planning without LLM
dependency, adhering to clean architecture domain boundaries.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

MIN_TASK_MINUTES = 25
MAX_SINGLE_TASK_MINUTES = 90
DEFAULT_DAILY_HOURS = 2.0


@dataclass(frozen=True)
class TopicWeight:
    """Academic topic with optional priority or difficulty weight."""

    name: str
    weight: float = 1.0

    def __post_init__(self) -> None:
        if not self.name.strip():
            msg = "Topic name cannot be empty"
            raise ValueError(msg)
        if self.weight <= 0:
            msg = f"Topic weight must be positive, got {self.weight}"
            raise ValueError(msg)


@dataclass(frozen=True)
class ScheduledTask:
    """A concrete dated study session task."""

    date: date
    topic: str
    minutes: int


@dataclass(frozen=True)
class PlanSchedule:
    """Generated day-by-day study schedule and feasibility metadata."""

    tasks: list[ScheduledTask]
    start_date: date
    exam_date: date
    total_days: int
    total_minutes: int
    daily_minutes_capacity: int
    is_feasible: bool
    warning: str | None = None
    uncovered_topics: list[str] = field(default_factory=list)


def resolve_current_date(
    clock: Callable[[], datetime] | None = None,
    user_timezone: str = "UTC",
) -> date:
    """Resolve current calendar date in the user's localized timezone."""
    now_utc = clock() if clock is not None else datetime.now(UTC)
    tz: tzinfo
    try:
        tz = ZoneInfo(user_timezone)
    except (ZoneInfoNotFoundError, ValueError):
        tz = UTC
    return now_utc.astimezone(tz).date()


def generate_study_plan(
    exam_date: date,
    topics: Sequence[str | TopicWeight],
    hours_per_day: float = DEFAULT_DAILY_HOURS,
    user_timezone: str = "UTC",
    clock: Callable[[], datetime] | None = None,
    start_date: date | None = None,
) -> PlanSchedule:
    """Generate a deterministic study plan distributing topics across available days.

    Args:
        exam_date: Target examination date.
        topics: Sequence of topic names or TopicWeight objects.
        hours_per_day: Daily study capacity in hours.
        user_timezone: IANA timezone string for calendar day resolution.
        clock: Optional time supplier for deterministic testing.
        start_date: Optional explicit start date override (defaults to current date).

    Returns:
        PlanSchedule containing dated tasks, feasibility assessment, and warnings.
    """
    effective_start = (
        start_date
        if start_date is not None
        else resolve_current_date(clock, user_timezone=user_timezone)
    )

    daily_capacity = max(15, min(1440, int(round(hours_per_day * 60))))

    # Normalize topics
    normalized_weights: list[TopicWeight] = []
    for item in topics:
        if isinstance(item, str):
            clean = item.strip()
            if clean:
                normalized_weights.append(TopicWeight(name=clean, weight=1.0))
        elif isinstance(item, TopicWeight):
            normalized_weights.append(item)

    if not normalized_weights:
        return PlanSchedule(
            tasks=[],
            start_date=effective_start,
            exam_date=exam_date,
            total_days=0,
            total_minutes=0,
            daily_minutes_capacity=daily_capacity,
            is_feasible=False,
            warning="Please provide at least one topic for your study plan.",
            uncovered_topics=[],
        )

    # Validate exam date strictly in the future
    days_available = (exam_date - effective_start).days
    if days_available <= 0:
        return PlanSchedule(
            tasks=[],
            start_date=effective_start,
            exam_date=exam_date,
            total_days=0,
            total_minutes=0,
            daily_minutes_capacity=daily_capacity,
            is_feasible=False,
            warning="Exam date must be after today.",
            uncovered_topics=[t.name for t in normalized_weights],
        )

    all_dates = [effective_start + timedelta(days=i) for i in range(days_available)]
    num_days = len(all_dates)

    # Determine review days and learning days
    if num_days == 1:
        review_dates = [all_dates[0]]
        learning_dates: list[date] = []
    elif num_days <= 6:
        review_dates = [all_dates[-1]]
        learning_dates = all_dates[:-1]
    else:
        review_dates = all_dates[-2:]
        learning_dates = all_dates[:-2]

    # Calculate required and available capacities
    total_learning_capacity = len(learning_dates) * daily_capacity
    min_needed_learning = len(normalized_weights) * MIN_TASK_MINUTES

    is_feasible = True
    warning: str | None = None
    uncovered: list[str] = []

    # Feasibility check: Can we allocate minimum time to every topic?
    if learning_dates and total_learning_capacity < min_needed_learning:
        is_feasible = False
        warning = (
            f"Only {days_available} days remaining before the exam. "
            "Study capacity is tight to cover all topics thoroughly."
        )

    # Allocate learning minutes per topic proportional to weight
    total_weight = sum(t.weight for t in normalized_weights)
    topic_allocations: dict[str, int] = {}
    for tw in normalized_weights:
        if learning_dates:
            target = int(round((tw.weight / total_weight) * total_learning_capacity))
            topic_allocations[tw.name] = max(0, target)
        else:
            # 1-day plan: partition daily capacity among topics
            target = int(round((tw.weight / total_weight) * daily_capacity))
            topic_allocations[tw.name] = max(0, target)

    tasks: list[ScheduledTask] = []

    if not learning_dates:
        # Single day before exam: split daily capacity between review and key topics
        day = review_dates[0]
        remaining_day_cap = daily_capacity
        review_minutes = max(MIN_TASK_MINUTES, remaining_day_cap // 3)
        tasks.append(
            ScheduledTask(
                date=day,
                topic="Final Review & Practice Exam",
                minutes=review_minutes,
            )
        )
        remaining_day_cap -= review_minutes

        for tw in sorted(normalized_weights, key=lambda x: -x.weight):
            if remaining_day_cap >= MIN_TASK_MINUTES:
                chunk = min(remaining_day_cap, max(MIN_TASK_MINUTES, remaining_day_cap // 2))
                tasks.append(ScheduledTask(date=day, topic=tw.name, minutes=chunk))
                remaining_day_cap -= chunk
            else:
                uncovered.append(tw.name)

        if uncovered:
            is_feasible = False
            warning = "Exam is tomorrow. Focused on top priority topics and final review."

        return PlanSchedule(
            tasks=tasks,
            start_date=effective_start,
            exam_date=exam_date,
            total_days=1,
            total_minutes=sum(t.minutes for t in tasks),
            daily_minutes_capacity=daily_capacity,
            is_feasible=is_feasible,
            warning=warning,
            uncovered_topics=uncovered,
        )

    # Multi-day scheduling: distribute topics across learning days
    # Maintain remaining needed minutes per topic
    remaining_topic_minutes = dict(topic_allocations)
    active_topics = [tw.name for tw in normalized_weights if remaining_topic_minutes[tw.name] > 0]
    topic_cursor = 0

    covered_topics: set[str] = set()

    for current_day in learning_dates:
        day_minutes_left = daily_capacity

        while day_minutes_left >= MIN_TASK_MINUTES and active_topics:
            current_topic = active_topics[topic_cursor % len(active_topics)]
            topic_needed = remaining_topic_minutes[current_topic]

            if topic_needed <= 0:
                active_topics.remove(current_topic)
                if not active_topics:
                    break
                topic_cursor = topic_cursor % len(active_topics)
                continue

            chunk = min(day_minutes_left, topic_needed, MAX_SINGLE_TASK_MINUTES)
            if chunk < MIN_TASK_MINUTES:
                chunk = min(day_minutes_left, MIN_TASK_MINUTES)

            tasks.append(
                ScheduledTask(
                    date=current_day,
                    topic=current_topic,
                    minutes=chunk,
                )
            )
            covered_topics.add(current_topic)
            remaining_topic_minutes[current_topic] -= chunk
            day_minutes_left -= chunk

            if remaining_topic_minutes[current_topic] <= 0 and current_topic in active_topics:
                active_topics.remove(current_topic)

            topic_cursor += 1

    # Check for uncovered topics
    for tw in normalized_weights:
        if tw.name not in covered_topics:
            uncovered.append(tw.name)

    if uncovered:
        is_feasible = False
        warning = (
            f"Could not fit {len(uncovered)} topics in the schedule. "
            "Consider increasing daily study hours or extending preparation time."
        )

    # Schedule Review Days (last days before exam)
    if len(review_dates) == 1:
        rev_day = review_dates[0]
        tasks.append(
            ScheduledTask(
                date=rev_day,
                topic="Comprehensive Review & Practice Questions",
                minutes=daily_capacity,
            )
        )
    elif len(review_dates) == 2:
        rev_day_1 = review_dates[0]
        rev_day_2 = review_dates[1]
        half_cap = daily_capacity // 2
        tasks.append(
            ScheduledTask(
                date=rev_day_1,
                topic="Weak Areas Review & Practice Tests",
                minutes=daily_capacity,
            )
        )
        tasks.append(
            ScheduledTask(
                date=rev_day_2,
                topic="Final Formulae & Flashcard Review",
                minutes=half_cap,
            )
        )
        tasks.append(
            ScheduledTask(
                date=rev_day_2,
                topic="Rest & Exam Readiness Buffer",
                minutes=daily_capacity - half_cap,
            )
        )

    total_minutes = sum(t.minutes for t in tasks)

    return PlanSchedule(
        tasks=tasks,
        start_date=effective_start,
        exam_date=exam_date,
        total_days=num_days,
        total_minutes=total_minutes,
        daily_minutes_capacity=daily_capacity,
        is_feasible=is_feasible,
        warning=warning,
        uncovered_topics=uncovered,
    )
