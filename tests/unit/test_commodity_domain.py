"""Unit tests for agricultural commodity domain, resolvers, and unit normalization (T12.3)."""

from __future__ import annotations

import pytest

from sahayak.core.errors import InvalidInputError
from sahayak.modules.local_info.domain.commodity import (
    CommodityTrend,
    PriceRecord,
    format_comparison_spoken,
    format_price_spoken,
    format_trend_spoken,
    resolve_commodity,
    resolve_market,
)


def test_commodity_resolution_english_and_hindi() -> None:
    # Wheat / Gehun
    assert resolve_commodity("wheat") == "Wheat"
    assert resolve_commodity("gehun") == "Wheat"
    assert resolve_commodity("gehu") == "Wheat"
    assert resolve_commodity("atta") == "Wheat"

    # Onion / Pyaz
    assert resolve_commodity("onion") == "Onion"
    assert resolve_commodity("pyaz") == "Onion"
    assert resolve_commodity("pyaaz") == "Onion"
    assert resolve_commodity("kanda") == "Onion"

    # Potato / Aloo
    assert resolve_commodity("potato") == "Potato"
    assert resolve_commodity("aloo") == "Potato"
    assert resolve_commodity("alu") == "Potato"

    # Tomato / Tamatar
    assert resolve_commodity("tomato") == "Tomato"
    assert resolve_commodity("tamatar") == "Tomato"

    # Gram / Chana
    assert resolve_commodity("chana") == "Gram (Chana)"
    assert resolve_commodity("gram") == "Gram (Chana)"

    # Mustard / Sarson
    assert resolve_commodity("mustard") == "Mustard"
    assert resolve_commodity("sarson") == "Mustard"


def test_commodity_resolution_fuzzy_and_fillers() -> None:
    assert resolve_commodity("onion price") == "Onion"
    assert resolve_commodity("wheat mandi rate") == "Wheat"
    assert resolve_commodity("tamator") == "Tomato"
    assert resolve_commodity("gehun bhav") == "Wheat"


def test_commodity_resolution_unknown_raises_invalid_input() -> None:
    with pytest.raises(InvalidInputError) as exc_info:
        resolve_commodity("Kryptonite mineral")
    assert "could not find commodity data" in exc_info.value.spoken
    assert exc_info.value.code == "invalid_input"

    with pytest.raises(InvalidInputError):
        resolve_commodity("   ")


def test_market_resolution() -> None:
    assert resolve_market("azadpur") == ("Azadpur", "NCT of Delhi")
    assert resolve_market("ghazipur") == ("Ghazipur", "NCT of Delhi")
    assert resolve_market("lasalgaon") == ("Lasalgaon", "Maharashtra")
    assert resolve_market("khanna") == ("Khanna", "Punjab")
    # Default when empty
    assert resolve_market(None) == ("Azadpur", "NCT of Delhi")
    assert resolve_market("") == ("Azadpur", "NCT of Delhi")


def test_unit_normalization_quintal_to_kg() -> None:
    # 2,450 per quintal = 24.5 per kg
    record = PriceRecord(
        commodity="Wheat",
        market="Azadpur",
        state="NCT of Delhi",
        arrival_date="2026-10-24",
        min_price_quintal=2300,
        max_price_quintal=2600,
        modal_price_quintal=2450,
    )
    assert record.modal_price_kg == 24.50
    assert record.min_price_kg == 23.00
    assert record.max_price_kg == 26.00


def test_format_price_spoken_fresh_and_stale() -> None:
    record = PriceRecord(
        commodity="Onion",
        market="Azadpur",
        state="NCT of Delhi",
        arrival_date="2026-10-24",
        min_price_quintal=2800,
        max_price_quintal=3400,
        modal_price_quintal=3000,
    )

    # Fresh price
    spoken_fresh = format_price_spoken(record, days_old=0, is_stale=False)
    assert len(spoken_fresh) <= 300
    assert "Onion in Azadpur mandi is trading at 3,000 rupees per quintal" in spoken_fresh
    assert "about 30 rupees per kilogram" in spoken_fresh
    assert "closed" not in spoken_fresh
    assert "*" not in spoken_fresh

    # Stale weekend / market closed price (e.g. 2 days old)
    spoken_stale = format_price_spoken(record, days_old=2, is_stale=True)
    assert len(spoken_stale) <= 300
    assert "Note: Rates are from 2 days ago as markets may have been closed" in spoken_stale


def test_format_comparison_spoken() -> None:
    r1 = PriceRecord(
        commodity="Tomato",
        market="Azadpur",
        state="NCT of Delhi",
        arrival_date="2026-10-24",
        min_price_quintal=2200,
        max_price_quintal=2600,
        modal_price_quintal=2400,
    )
    r2 = PriceRecord(
        commodity="Tomato",
        market="Ghazipur",
        state="NCT of Delhi",
        arrival_date="2026-10-24",
        min_price_quintal=2000,
        max_price_quintal=2400,
        modal_price_quintal=2200,
    )

    spoken = format_comparison_spoken("Tomato", [r1, r2])
    assert len(spoken) <= 300
    assert (
        "Tomato prices: Azadpur is 24 rupees per kg, while Ghazipur is 22 rupees per kg" in spoken
    )


def test_format_trend_spoken() -> None:
    trend_up = CommodityTrend(
        commodity="Potato",
        market="Azadpur",
        current_modal_kg=22.0,
        previous_modal_kg=19.0,
        change_pct=15.8,
        direction="up",
    )
    spoken_up = format_trend_spoken(trend_up)
    assert len(spoken_up) <= 300
    assert "Potato prices in Azadpur rose by 16 percent" in spoken_up

    trend_steady = CommodityTrend(
        commodity="Wheat",
        market="Khanna",
        current_modal_kg=25.0,
        previous_modal_kg=25.0,
        change_pct=0.0,
        direction="steady",
    )
    spoken_steady = format_trend_spoken(trend_steady)
    assert len(spoken_steady) <= 300
    assert "have stayed steady over the past week" in spoken_steady
