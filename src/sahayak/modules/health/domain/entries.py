"""Domain models, plausibility validation, and voice formatters for health logs (T7.1).

Logging personal health metrics only; zero medical advice provided (PRD §1.4).
"""

from __future__ import annotations

import re
from typing import Any

from sahayak.core.errors import InvalidInputError

HEALTH_DISCLAIMER = (
    "Sahayak health logging is for personal tracking only and does not "
    "provide medical advice or diagnosis."
)

SUPPORTED_KINDS = {"water", "meal", "workout", "sleep", "weight"}


def normalize_health_kind(kind: str | None) -> str:
    """Normalize and validate health log kind."""
    if not kind:
        raise InvalidInputError(
            "Health entry kind is required (water, meal, workout, sleep, weight)."
        )
    clean = kind.strip().lower()
    if clean not in SUPPORTED_KINDS:
        kinds_str = ", ".join(sorted(SUPPORTED_KINDS))
        raise InvalidInputError(f"Unsupported health kind '{kind}'. Expected one of: {kinds_str}.")
    return clean


def validate_water_entry(value: float | int | str | None, unit: str | None) -> dict[str, Any]:
    """Validate and normalize water consumption entry."""
    if value is None:
        raise InvalidInputError("Water amount is required (e.g. 500 ml or 2 cups).")

    val_float = _parse_numeric(value)
    u_clean = (unit or "ml").strip().lower()

    # Convert to ml
    if u_clean in ("ml", "milliliter", "milliliters"):
        ml = round(val_float)
    elif u_clean in ("l", "liter", "liters", "litre", "litres"):
        ml = round(val_float * 1000)
    elif u_clean in ("oz", "fl oz", "ounce", "ounces"):
        ml = round(val_float * 29.5735)
    elif u_clean in ("cup", "cups"):
        ml = round(val_float * 240)
    elif u_clean in ("glass", "glasses"):
        ml = round(val_float * 250)
    else:
        raise InvalidInputError(
            f"Unsupported water unit '{unit}'. Please use ml, liters, oz, cups, or glasses."
        )

    # Plausibility check: 50 ml to 5,000 ml
    if ml < 50 or ml > 5000:
        raise InvalidInputError(
            f"I cannot log {value} {unit or 'ml'} of water. "
            "Please specify a plausible amount between 50 ml and 5000 ml."
        )

    return {
        "amount_ml": ml,
        "input_value": val_float,
        "input_unit": u_clean,
    }


def validate_weight_entry(value: float | int | str | None, unit: str | None) -> dict[str, Any]:
    """Validate and normalize body weight entry."""
    if value is None:
        raise InvalidInputError("Weight value is required (e.g. 72.5 kg or 160 lbs).")

    val_float = _parse_numeric(value)
    u_clean = (unit or "kg").strip().lower()

    # Convert to kg
    if u_clean in ("kg", "kgs", "kilogram", "kilograms"):
        kg = round(val_float, 2)
    elif u_clean in ("lb", "lbs", "pound", "pounds"):
        kg = round(val_float * 0.453592, 2)
    else:
        raise InvalidInputError(f"Unsupported weight unit '{unit}'. Please use kg or lbs.")

    # Plausibility check: 20 kg to 500 kg
    if kg < 20.0 or kg > 500.0:
        raise InvalidInputError(
            f"I cannot log {value} {unit or 'kg'}. "
            "Please specify a plausible weight between 20 kg and 500 kg."
        )

    return {
        "weight_kg": kg,
        "input_value": val_float,
        "input_unit": u_clean,
    }


def validate_sleep_entry(value: float | int | str | None, unit: str | None) -> dict[str, Any]:
    """Validate and normalize sleep duration entry."""
    if value is None:
        raise InvalidInputError("Sleep duration is required (e.g. 7.5 hours or 480 minutes).")

    val_float = _parse_numeric(value)
    u_clean = (unit or "hours").strip().lower()

    if u_clean in ("hour", "hours", "hr", "hrs", "h"):
        hours = round(val_float, 2)
    elif u_clean in ("minute", "minutes", "min", "mins", "m"):
        hours = round(val_float / 60.0, 2)
    else:
        raise InvalidInputError(f"Unsupported sleep unit '{unit}'. Please use hours or minutes.")

    # Plausibility check: 0.5 hours to 24 hours
    if hours < 0.5 or hours > 24.0:
        raise InvalidInputError(
            f"I cannot log {value} {unit or 'hours'} of sleep. "
            "Please specify a plausible duration between 30 minutes and 24 hours."
        )

    return {
        "duration_hours": hours,
        "duration_minutes": round(hours * 60),
        "input_value": val_float,
        "input_unit": u_clean,
    }


def validate_workout_entry(
    activity: str | None,
    duration: float | int | str | None,
    unit: str | None = "minutes",
    intensity: str | None = None,
) -> dict[str, Any]:
    """Validate and normalize workout activity entry."""
    if not activity or not activity.strip():
        raise InvalidInputError(
            "Workout activity name is required (e.g. 'running', 'yoga', 'cycling')."
        )

    dur_val = 30.0 if duration is None else _parse_numeric(duration)
    u_clean = (unit or "minutes").strip().lower()

    if u_clean in ("minute", "minutes", "min", "mins", "m"):
        minutes = round(dur_val)
    elif u_clean in ("hour", "hours", "hr", "hrs", "h"):
        minutes = round(dur_val * 60)
    else:
        raise InvalidInputError(f"Unsupported duration unit '{unit}'. Please use minutes or hours.")

    # Plausibility check: 1 to 600 minutes (10 hours)
    if minutes < 1 or minutes > 600:
        raise InvalidInputError(
            f"I cannot log a workout duration of {duration} {unit}. "
            "Please specify a duration between 1 minute and 10 hours."
        )

    data: dict[str, Any] = {
        "activity": activity.strip(),
        "duration_minutes": minutes,
    }
    if intensity:
        int_clean = intensity.strip().lower()
        if int_clean in ("low", "medium", "moderate", "high", "vigorous"):
            data["intensity"] = int_clean

    return data


def validate_meal_entry(
    meal_name: str | None,
    meal_type: str | None = None,
    calories: int | str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Validate and normalize meal log entry."""
    if not meal_name or not meal_name.strip():
        raise InvalidInputError("Meal description is required (e.g. 'oatmeal with banana').")

    m_type = (meal_type or "meal").strip().lower()
    valid_types = {"breakfast", "lunch", "dinner", "snack", "meal"}
    if m_type not in valid_types:
        m_type = "meal"

    data: dict[str, Any] = {
        "description": meal_name.strip(),
        "meal_type": m_type,
    }

    if calories is not None:
        cal_val = _parse_numeric(calories)
        cal_int = round(cal_val)
        if cal_int < 10 or cal_int > 10000:
            raise InvalidInputError(
                f"I cannot log {calories} calories. "
                "Please specify a plausible calorie estimate between 10 and 10000 kcal."
            )
        data["calories"] = cal_int

    if notes and notes.strip():
        data["notes"] = notes.strip()

    return data


def format_health_logged_spoken(kind: str, data: dict[str, Any]) -> str:
    """Format voice spoken summary for logged health entry under 300 characters."""
    if kind == "water":
        ml = data.get("amount_ml", 0)
        return f"Logged {ml} ml of water."

    if kind == "weight":
        kg = data.get("weight_kg", 0)
        return f"Logged your weight as {kg} kilograms."

    if kind == "sleep":
        hrs = data.get("duration_hours", 0)
        return f"Logged {hrs} hours of sleep."

    if kind == "workout":
        act = data.get("activity", "workout")
        mins = data.get("duration_minutes", 0)
        return f"Logged {mins} minutes of {act}."

    if kind == "meal":
        desc = data.get("description", "meal")
        m_type = data.get("meal_type", "meal")
        cals = data.get("calories")
        msg = f"Logged {m_type}: {desc}"
        if cals:
            msg += f" at {cals} calories."
        else:
            msg += "."
        return msg

    return f"Logged {kind} entry."


def format_health_undo_spoken(kind: str, data: dict[str, Any]) -> str:
    """Format voice spoken summary for undoing a health entry."""
    if kind == "water":
        ml = data.get("amount_ml", 0)
        return f"Undid your last water log of {ml} ml."
    if kind == "weight":
        kg = data.get("weight_kg", 0)
        return f"Undid your last weight entry of {kg} kilograms."
    if kind == "sleep":
        hrs = data.get("duration_hours", 0)
        return f"Undid your last sleep entry of {hrs} hours."
    if kind == "workout":
        act = data.get("activity", "workout")
        return f"Undid your last workout log for {act}."
    if kind == "meal":
        desc = data.get("description", "meal")
        return f"Undid your last meal log for {desc}."

    return f"Undid your last {kind} entry."


def format_health_list_spoken(kind: str | None, entries: list[dict[str, Any]]) -> str:
    """Format voice spoken summary for listed health entries."""
    if not entries:
        kind_str = f" for {kind}" if kind else ""
        return f"You have no recent health logs{kind_str}."

    items: list[str] = []
    for e in entries[:4]:
        k = e.get("kind", "")
        d = e.get("data", {})
        if k == "water":
            items.append(f"{d.get('amount_ml', 0)} ml water")
        elif k == "weight":
            items.append(f"{d.get('weight_kg', 0)} kg weight")
        elif k == "sleep":
            items.append(f"{d.get('duration_hours', 0)} hours sleep")
        elif k == "workout":
            items.append(f"{d.get('duration_minutes', 0)} min {d.get('activity', 'workout')}")
        elif k == "meal":
            items.append(f"{d.get('meal_type', 'meal')} {d.get('description', '')}")

    joined = ", ".join(items)
    msg = f"Your recent logs: {joined}."
    if len(msg) > 300:
        msg = msg[:297] + "..."
    return msg


def _parse_numeric(value: float | int | str) -> float:
    """Safely extract float from string or number."""
    if isinstance(value, int | float):
        return float(value)
    cleaned = re.sub(r"[^\d.-]", "", str(value).strip())
    try:
        return float(cleaned)
    except ValueError as err:
        raise InvalidInputError(f"Could not parse numeric value from '{value}'") from err
