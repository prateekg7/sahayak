"""Unit tests for health summary domain calculations, adherence, and formatters (T7.2)."""

from datetime import date

from sahayak.modules.health.domain.summary import (
    calculate_today_summary,
    calculate_weekly_summary,
    format_health_today_spoken,
    format_health_week_spoken,
    format_medicine_added_spoken,
    format_medicine_marked_spoken,
    format_medicines_due_spoken,
    is_medicine_scheduled_on_date,
)


class TestMedicineScheduleEvaluation:
    """Test medicine schedule evaluation against dates and days of week."""

    def test_daily_medicine(self) -> None:
        start = date(2026, 3, 1)
        end = date(2026, 3, 31)

        # Before start date
        assert not is_medicine_scheduled_on_date(start, end, None, date(2026, 2, 28))
        # Active date
        assert is_medicine_scheduled_on_date(start, end, None, date(2026, 3, 15))
        # After end date
        assert not is_medicine_scheduled_on_date(start, end, None, date(2026, 4, 1))

    def test_weekday_restricted_medicine(self) -> None:
        start = date(2026, 3, 1)  # Sunday
        days = ["mon", "wed", "fri"]

        # 2026-03-01 is Sunday -> False
        assert not is_medicine_scheduled_on_date(start, None, days, date(2026, 3, 1))
        # 2026-03-02 is Monday -> True
        assert is_medicine_scheduled_on_date(start, None, days, date(2026, 3, 2))
        # 2026-03-03 is Tuesday -> False
        assert not is_medicine_scheduled_on_date(start, None, days, date(2026, 3, 3))
        # 2026-03-04 is Wednesday -> True
        assert is_medicine_scheduled_on_date(start, None, days, date(2026, 3, 4))


class TestHealthCalculations:
    """Test daily aggregates and weekly averages."""

    def test_calculate_today_summary(self) -> None:
        entries = [
            {"kind": "water", "data": {"amount_ml": 500}},
            {"kind": "water", "data": {"amount_ml": 750}},
            {"kind": "workout", "data": {"duration_minutes": 35}},
            {"kind": "sleep", "data": {"duration_hours": 7.5}},
            {"kind": "meal", "data": {"calories": 450}},
            {"kind": "weight", "data": {"weight_kg": 73.0}},
        ]

        summary = calculate_today_summary(entries, scheduled_doses_count=2, taken_doses_count=1)
        assert summary["water_ml"] == 1250
        assert summary["workout_minutes"] == 35
        assert summary["sleep_hours"] == 7.5
        assert summary["meals_count"] == 1
        assert summary["calories"] == 450
        assert summary["weight_kg"] == 73.0
        assert summary["medicines_due_count"] == 2
        assert summary["medicines_taken_count"] == 1

    def test_calculate_weekly_summary(self) -> None:
        entries = [
            {"kind": "water", "data": {"amount_ml": 1400}, "occurred_at": "2026-03-15T10:00:00Z"},
            {"kind": "water", "data": {"amount_ml": 2100}, "occurred_at": "2026-03-16T10:00:00Z"},
            {
                "kind": "workout",
                "data": {"duration_minutes": 45},
                "occurred_at": "2026-03-15T10:00:00Z",
            },
            {
                "kind": "workout",
                "data": {"duration_minutes": 45},
                "occurred_at": "2026-03-16T10:00:00Z",
            },
            {
                "kind": "sleep",
                "data": {"duration_hours": 8.0},
                "occurred_at": "2026-03-15T07:00:00Z",
            },
            {
                "kind": "sleep",
                "data": {"duration_hours": 7.0},
                "occurred_at": "2026-03-16T07:00:00Z",
            },
        ]

        summary = calculate_weekly_summary(entries, scheduled_doses_count=10, taken_doses_count=8)
        assert summary["avg_daily_water_ml"] == round((1400 + 2100) / 7)
        assert summary["total_workout_minutes"] == 90
        assert summary["avg_daily_sleep_hours"] == 7.5
        assert summary["medicine_adherence_percent"] == 80.0


class TestSummarySpokenFormatters:
    """Test voice output formatters."""

    def test_format_today_spoken(self) -> None:
        summary = {
            "water_ml": 1500,
            "workout_minutes": 30,
            "sleep_hours": 7.5,
            "medicines_due_count": 2,
            "medicines_taken_count": 2,
        }
        sp = format_health_today_spoken(summary)
        expected = (
            "Today you logged: 1500 ml water, 30 minutes of exercise, "
            "7.5 hours of sleep, 2 of 2 medicines taken."
        )
        assert sp == expected
        assert len(sp) < 300

    def test_format_week_spoken(self) -> None:
        summary = {
            "avg_daily_water_ml": 1800,
            "total_workout_minutes": 120,
            "avg_daily_sleep_hours": 7.2,
            "medicine_adherence_percent": 90.0,
        }
        sp = format_health_week_spoken(summary)
        expected = (
            "Past 7 days: daily average of 1800 ml water, 7.2 hours sleep, "
            "120 total workout minutes, 90.0% medicine adherence."
        )
        assert sp == expected
        assert len(sp) < 300

    def test_format_medicines_due_spoken(self) -> None:
        due = [
            {"name": "Vitamin D", "scheduled_time": "09:00", "status": "pending"},
            {"name": "Omega 3", "scheduled_time": "13:00", "status": "pending"},
        ]
        sp = format_medicines_due_spoken(due)
        expected = "You have 2 medicine doses pending today: Vitamin D at 09:00, Omega 3 at 13:00."
        assert sp == expected

        all_taken = [
            {"name": "Vitamin D", "scheduled_time": "09:00", "status": "taken"},
        ]
        sp_taken = format_medicines_due_spoken(all_taken)
        assert "All your scheduled medicines for today are marked as taken." in sp_taken

    def test_format_medicine_marked_spoken(self) -> None:
        sp = format_medicine_marked_spoken("Metformin", "09:00")
        assert sp == "Marked your Metformin for 09:00 as taken."

    def test_format_medicine_added_spoken(self) -> None:
        sp = format_medicine_added_spoken("Aspirin", ["08:00", "20:00"])
        assert "Added Aspirin to your schedule at 08:00, 20:00." in sp
        assert "no dosing advice" in sp
