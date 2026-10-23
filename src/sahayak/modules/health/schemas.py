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
