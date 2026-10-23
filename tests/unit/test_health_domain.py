"""Unit tests for health domain models, plausibility validation, and voice formatters (T7.1)."""

import pytest

from sahayak.core.errors import InvalidInputError
from sahayak.modules.health.domain.entries import (
    HEALTH_DISCLAIMER,
    format_health_list_spoken,
    format_health_logged_spoken,
    normalize_health_kind,
    validate_meal_entry,
    validate_sleep_entry,
    validate_water_entry,
    validate_weight_entry,
    validate_workout_entry,
)


class TestHealthValidation:
    """Test health domain validations and plausibility bounds."""

    def test_normalize_kind(self) -> None:
        assert normalize_health_kind("WATER") == "water"
        assert normalize_health_kind("  Sleep ") == "sleep"
        with pytest.raises(InvalidInputError, match="Health entry kind is required"):
            normalize_health_kind(None)
        with pytest.raises(InvalidInputError, match="Unsupported health kind"):
            normalize_health_kind("blood_pressure_treatment")

    def test_water_validation_valid_units(self) -> None:
        # ml
        w1 = validate_water_entry(500, "ml")
        assert w1["amount_ml"] == 500

        # liters
        w2 = validate_water_entry(1.5, "liters")
        assert w2["amount_ml"] == 1500

        # cups (240ml)
        w3 = validate_water_entry(2, "cups")
        assert w3["amount_ml"] == 480

        # oz (29.5735ml)
        w4 = validate_water_entry(16, "oz")
        assert w4["amount_ml"] == 473

        # glasses (250ml)
        w5 = validate_water_entry(3, "glasses")
        assert w5["amount_ml"] == 750

    def test_water_validation_plausibility(self) -> None:
        # Lower bound (< 50ml)
        with pytest.raises(InvalidInputError, match="plausible amount between 50 ml and 5000 ml"):
            validate_water_entry(10, "ml")

        # Upper bound (> 5000ml)
        with pytest.raises(InvalidInputError, match="plausible amount between 50 ml and 5000 ml"):
            validate_water_entry(6000, "ml")

        # Unsupported unit
        with pytest.raises(InvalidInputError, match="Unsupported water unit"):
            validate_water_entry(500, "gallons")

    def test_weight_validation(self) -> None:
        # kg
        wt1 = validate_weight_entry(72.5, "kg")
        assert wt1["weight_kg"] == 72.5

        # lbs to kg
        wt2 = validate_weight_entry(165, "lbs")
        assert 74.0 <= wt2["weight_kg"] <= 75.5

        # Lower bound (< 20kg)
        with pytest.raises(InvalidInputError, match="between 20 kg and 500 kg"):
            validate_weight_entry(15, "kg")

        # Upper bound (> 500kg)
        with pytest.raises(InvalidInputError, match="between 20 kg and 500 kg"):
            validate_weight_entry(600, "kg")

        # Unsupported unit
        with pytest.raises(InvalidInputError, match="Unsupported weight unit"):
            validate_weight_entry(70, "stones")

    def test_sleep_validation(self) -> None:
        # hours
        s1 = validate_sleep_entry(7.5, "hours")
        assert s1["duration_hours"] == 7.5
        assert s1["duration_minutes"] == 450

        # minutes
        s2 = validate_sleep_entry(480, "minutes")
        assert s2["duration_hours"] == 8.0
        assert s2["duration_minutes"] == 480

        # Plausibility bounds (< 0.5hr or > 24hr)
        with pytest.raises(InvalidInputError, match="between 30 minutes and 24 hours"):
            validate_sleep_entry(0.2, "hours")

        with pytest.raises(InvalidInputError, match="between 30 minutes and 24 hours"):
            validate_sleep_entry(26, "hours")

    def test_workout_validation(self) -> None:
        # valid workout
        w1 = validate_workout_entry("Morning jog", 45, "minutes", "moderate")
        assert w1["activity"] == "Morning jog"
        assert w1["duration_minutes"] == 45
        assert w1["intensity"] == "moderate"

        # hours conversion
        w2 = validate_workout_entry("Cycling", 1.5, "hours")
        assert w2["duration_minutes"] == 90

        # Plausibility bounds (< 1min or > 600min)
        with pytest.raises(InvalidInputError, match="between 1 minute and 10 hours"):
            validate_workout_entry("Sprints", 0, "minutes")

        with pytest.raises(InvalidInputError, match="between 1 minute and 10 hours"):
            validate_workout_entry("Walk", 700, "minutes")

        # Missing activity
        with pytest.raises(InvalidInputError, match="Workout activity name is required"):
            validate_workout_entry("", 30)

    def test_meal_validation(self) -> None:
        # valid meal
        m1 = validate_meal_entry("Scrambled eggs and toast", "breakfast", 450, "felt energized")
        assert m1["description"] == "Scrambled eggs and toast"
        assert m1["meal_type"] == "breakfast"
        assert m1["calories"] == 450
        assert m1["notes"] == "felt energized"

        # calorie bounds
        with pytest.raises(InvalidInputError, match="between 10 and 10000 kcal"):
            validate_meal_entry("Snack", "snack", 5)

        with pytest.raises(InvalidInputError, match="between 10 and 10000 kcal"):
            validate_meal_entry("Huge Feast", "dinner", 12000)

        # missing description
        with pytest.raises(InvalidInputError, match="Meal description is required"):
            validate_meal_entry("   ")


class TestHealthSpokenFormatting:
    """Test voice UX output strings (no markdown, concise, under 300 chars)."""

    def test_disclaimer_constant(self) -> None:
        assert "medical advice" in HEALTH_DISCLAIMER
        assert "personal tracking" in HEALTH_DISCLAIMER

    def test_format_logged_spoken(self) -> None:
        sp_water = format_health_logged_spoken("water", {"amount_ml": 500})
        assert "Logged 500 ml of water" in sp_water
        assert len(sp_water) < 300

        sp_wt = format_health_logged_spoken("weight", {"weight_kg": 72.5})
        assert "Logged your weight as 72.5 kilograms" in sp_wt
        assert len(sp_wt) < 300

        sp_sl = format_health_logged_spoken("sleep", {"duration_hours": 7.5})
        assert "Logged 7.5 hours of sleep" in sp_sl

        sp_wo = format_health_logged_spoken(
            "workout", {"activity": "running", "duration_minutes": 30}
        )
        assert "Logged 30 minutes of running" in sp_wo

        sp_ml = format_health_logged_spoken(
            "meal",
            {"meal_type": "lunch", "description": "salad bowl", "calories": 400},
        )
        assert "Logged lunch: salad bowl at 400 calories." in sp_ml

    def test_format_list_spoken(self) -> None:
        sp_empty = format_health_list_spoken("water", [])
        assert "You have no recent health logs for water." in sp_empty

        entries = [
            {"kind": "water", "data": {"amount_ml": 250}},
            {"kind": "water", "data": {"amount_ml": 500}},
        ]
        sp_list = format_health_list_spoken("water", entries)

        assert "Your recent logs: 250 ml water, 500 ml water." in sp_list
        assert len(sp_list) < 300
