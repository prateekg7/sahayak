"""Pydantic schemas for the health module (T7.1)."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from sahayak.modules.health.domain.entries import HEALTH_DISCLAIMER


class HealthLogAction(str, Enum):
    """Supported health log actions."""

    LOG = "log"
    LIST = "list"
    UNDO_LAST = "undo_last"
    DELETE = "delete"


class HealthKind(str, Enum):
    """Supported personal health metric kinds."""

    WATER = "water"
    MEAL = "meal"
    WORKOUT = "workout"
    SLEEP = "sleep"
    WEIGHT = "weight"


class HealthLogRequest(BaseModel):
    """Input payload for the 'health_log' MCP tool."""

    action: HealthLogAction = Field(
        default=HealthLogAction.LOG,
        description="Action: 'log', 'list', or 'undo_last'.",
    )
    kind: str | None = Field(
        default=None,
        description="Metric kind: 'water', 'meal', 'workout', 'sleep', or 'weight'.",
    )
    value: float | int | str | None = Field(
        default=None,
        description="Numeric metric (e.g. 500 for water, 72.5 for weight, 7.5 for sleep).",
    )

    unit: str | None = Field(
        default=None,
        description="Measurement unit: 'ml', 'oz', 'kg', 'lbs', 'hours', 'minutes'.",
    )
    meal_name: str | None = Field(
        default=None,
        description="Description of food eaten (e.g. 'oatmeal with berries').",
    )
    meal_type: str | None = Field(
        default=None,
        description="Meal classification: 'breakfast', 'lunch', 'dinner', 'snack'.",
    )
    activity: str | None = Field(
        default=None,
        description="Workout exercise name (e.g. 'running', 'yoga', 'cycling').",
    )
    duration: float | int | str | None = Field(
        default=None,
        description="Workout duration in minutes or hours.",
    )
    intensity: str | None = Field(
        default=None,
        description="Workout intensity: 'low', 'medium', 'high'.",
    )
    calories: int | str | None = Field(
        default=None,
        description="Estimated calorie intake for meal.",
    )
    notes: str | None = Field(
        default=None,
        max_length=255,
        description="Optional additional notes or context.",
    )
    entry_id: str | None = Field(
        default=None,
        description="Entry UUID for deletion.",
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Maximum entries to return for 'list'.",
    )
    request_id: str | None = Field(
        default=None,
        description="Optional idempotency key for mutations.",
    )


class HealthEntryData(BaseModel):
    """Representation of an individual health entry."""

    id: str
    user_id: str
    kind: str
    data: dict[str, Any]
    occurred_at: str | None = None


class HealthLogResponseData(BaseModel):
    """Output payload for the 'health_log' tool inside standard envelope."""

    action: str
    kind: str | None = None
    entry: HealthEntryData | None = None
    entries: list[HealthEntryData] = Field(default_factory=list)
    count: int = 0
    disclaimer: str = HEALTH_DISCLAIMER


class HealthSummaryAction(str, Enum):
    """Supported health summary and medicine actions."""

    TODAY = "today"
    WEEK = "week"
    MEDICINES_DUE = "medicines_due"
    MARK_TAKEN = "mark_taken"
    ADD_MEDICINE = "add_medicine"
    LIST_MEDICINES = "list_medicines"


class HealthSummaryRequest(BaseModel):
    """Input payload for the 'health_summary' MCP tool."""

    action: HealthSummaryAction = Field(
        default=HealthSummaryAction.TODAY,
        description="Action: 'today', 'week', 'medicines_due', 'mark_taken', 'add_medicine'.",
    )

    medicine_name: str | None = Field(
        default=None,
        description="Medicine name for tracking, e.g. 'Vitamin D' or 'Metformin'.",
    )
    scheduled_time: str | None = Field(
        default=None,
        description="Scheduled dose time in HH:MM format, e.g. '09:00'.",
    )
    dosage_text: str | None = Field(
        default="1 dose",
        description="User-defined dose note, e.g. '1 tablet'.",
    )
    times: list[str] | None = Field(
        default=None,
        description="List of daily times in HH:MM, e.g. ['09:00', '21:00'].",
    )
    days: list[str] | None = Field(
        default=None,
        description="Optional list of active weekdays, e.g. ['mon', 'wed', 'fri'].",
    )
    request_id: str | None = Field(
        default=None,
        description="Optional idempotency key for mutations.",
    )


class MedicineDueData(BaseModel):
    """Item representing a scheduled medicine dose for today."""

    id: str
    medicine_id: str
    name: str
    dosage_text: str
    scheduled_date: str
    scheduled_time: str
    status: str
    taken_at: str | None = None


class MedicineScheduleData(BaseModel):
    """Item representing a configured medicine schedule."""

    id: str
    name: str
    dosage_text: str
    times: list[str]
    days: list[str] | None = None
    is_active: bool = True


class HealthSummaryResponseData(BaseModel):
    """Output payload for the 'health_summary' MCP tool."""

    action: str
    period: str | None = None
    summary: dict[str, Any] = Field(default_factory=dict)
    medicines_due: list[MedicineDueData] = Field(default_factory=list)
    medicines: list[MedicineScheduleData] = Field(default_factory=list)
    disclaimer: str = HEALTH_DISCLAIMER
