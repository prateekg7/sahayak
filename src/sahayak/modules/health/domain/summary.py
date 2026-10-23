"""Domain logic, schedule evaluation, and voice formatters for health summaries (T7.2).

Tracking schedules and activity only; zero medical or dosing advice provided (PRD §1.4).
"""

from __future__ import annotations

from datetime import date
from typing import Any


def is_medicine_scheduled_on_date(
    start_date: date,
    end_date: date | None,
    days: list[str] | None,
    target_date: date,
) -> bool:
    """Determine if a medicine is scheduled on a given target date."""
    if target_date < start_date:
        return False
    if end_date and target_date > end_date:
        return False
    if not days:
        return True

    target_weekday = target_date.strftime("%a").lower()[:3]
    allowed_days = {d.strip().lower()[:3] for d in days}
    return target_weekday in allowed_days


def calculate_today_summary(
    entries: list[dict[str, Any]],
    scheduled_doses_count: int,
    taken_doses_count: int,
) -> dict[str, Any]:
    """Calculate aggregate health metrics for today."""
    water_ml = 0
    workout_minutes = 0
    sleep_hours = 0.0
    meals_count = 0
    calories = 0
    weight_kg: float | None = None

    for entry in entries:
        kind = entry.get("kind")
        data = entry.get("data", {})
        if kind == "water":
            water_ml += int(data.get("amount_ml", 0))
        elif kind == "workout":
            workout_minutes += int(data.get("duration_minutes", 0))
        elif kind == "sleep":
            sleep_hours += float(data.get("duration_hours", 0.0))
        elif kind == "meal":
            meals_count += 1
            if "calories" in data:
                calories += int(data.get("calories", 0))
        elif kind == "weight":
            weight_kg = float(data.get("weight_kg", 0.0))

    return {
        "water_ml": water_ml,
        "workout_minutes": workout_minutes,
        "sleep_hours": round(sleep_hours, 1),
        "meals_count": meals_count,
        "calories": calories,
        "weight_kg": weight_kg,
        "medicines_due_count": scheduled_doses_count,
        "medicines_taken_count": taken_doses_count,
    }


def calculate_weekly_summary(
    entries: list[dict[str, Any]],
    scheduled_doses_count: int,
    taken_doses_count: int,
) -> dict[str, Any]:
    """Calculate 7-day average health metrics and adherence rates."""
    total_water = 0
    total_workout = 0

    # Group sleep by date to average over days with sleep logs
    sleep_by_date: dict[str, float] = {}

    for entry in entries:
        kind = entry.get("kind")
        data = entry.get("data", {})
        occurred = entry.get("occurred_at")
        date_str = occurred[:10] if occurred else ""

        if kind == "water":
            total_water += int(data.get("amount_ml", 0))
        elif kind == "workout":
            total_workout += int(data.get("duration_minutes", 0))
        elif kind == "sleep":
            hrs = float(data.get("duration_hours", 0.0))
            sleep_by_date[date_str] = sleep_by_date.get(date_str, 0.0) + hrs

    avg_water_daily = round(total_water / 7)
    if sleep_by_date:
        avg_sleep_daily = round(sum(sleep_by_date.values()) / len(sleep_by_date), 1)
    else:
        avg_sleep_daily = 0.0

    if scheduled_doses_count > 0:
        adherence_rate = round((taken_doses_count / scheduled_doses_count) * 100, 1)
    else:
        adherence_rate = 100.0

    return {
        "days": 7,
        "avg_daily_water_ml": avg_water_daily,
        "total_workout_minutes": total_workout,
        "avg_daily_sleep_hours": avg_sleep_daily,
        "medicine_adherence_percent": adherence_rate,
        "scheduled_doses_count": scheduled_doses_count,
        "taken_doses_count": taken_doses_count,
    }


def format_health_today_spoken(summary: dict[str, Any]) -> str:
    """Format today's health summary into voice text under 300 characters."""
    parts = []
    w = summary.get("water_ml", 0)
    if w > 0:
        parts.append(f"{w} ml water")

    wo = summary.get("workout_minutes", 0)
    if wo > 0:
        parts.append(f"{wo} minutes of exercise")

    sl = summary.get("sleep_hours", 0.0)
    if sl > 0:
        parts.append(f"{sl} hours of sleep")

    due = summary.get("medicines_due_count", 0)
    taken = summary.get("medicines_taken_count", 0)
    if due > 0:
        parts.append(f"{taken} of {due} medicines taken")

    if not parts:
        return "No health activities logged today yet."

    return f"Today you logged: {', '.join(parts)}."


def format_health_week_spoken(summary: dict[str, Any]) -> str:
    """Format 7-day health summary into voice text under 300 characters."""
    w = summary.get("avg_daily_water_ml", 0)
    wo = summary.get("total_workout_minutes", 0)
    sl = summary.get("avg_daily_sleep_hours", 0.0)
    adh = summary.get("medicine_adherence_percent", 100.0)

    parts = [f"daily average of {w} ml water"]
    if sl > 0:
        parts.append(f"{sl} hours sleep")
    if wo > 0:
        parts.append(f"{wo} total workout minutes")
    parts.append(f"{adh}% medicine adherence")

    return f"Past 7 days: {', '.join(parts)}."


def format_medicines_due_spoken(due_items: list[dict[str, Any]]) -> str:
    """Format medicines due list into voice text under 300 characters."""
    pending = [m for m in due_items if m.get("status") == "pending"]
    if not pending:
        if due_items:
            return "All your scheduled medicines for today are marked as taken."
        return "You have no medicines scheduled for today."

    item_strs = []
    for m in pending[:3]:
        item_strs.append(f"{m.get('name')} at {m.get('scheduled_time')}")

    rem = len(pending) - 3
    extra = f" and {rem} more" if rem > 0 else ""
    return f"You have {len(pending)} medicine doses pending today: {', '.join(item_strs)}{extra}."


def format_medicine_marked_spoken(name: str, scheduled_time: str | None = None) -> str:
    """Format voice response when marking a medicine taken."""
    time_str = f" for {scheduled_time}" if scheduled_time else ""
    return f"Marked your {name}{time_str} as taken."


def format_medicine_added_spoken(name: str, times: list[str]) -> str:
    """Format voice response when adding a medicine schedule."""
    t_str = ", ".join(times)
    return f"Added {name} to your schedule at {t_str}. Note: no dosing advice is provided."
