"""Domain models, commodity/market resolvers, unit normalization, and speech formatters (T12.3)."""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from sahayak.core.errors import InvalidInputError

COMMODITY_ALIASES: dict[str, str] = {
    # Wheat
    "wheat": "Wheat",
    "gehun": "Wheat",
    "gehu": "Wheat",
    "atta": "Wheat",
    # Rice / Paddy
    "rice": "Rice",
    "chawal": "Rice",
    "dhan": "Rice",
    "paddy": "Rice",
    # Onion
    "onion": "Onion",
    "pyaz": "Onion",
    "pyaaz": "Onion",
    "kanda": "Onion",
    # Potato
    "potato": "Potato",
    "aloo": "Potato",
    "alu": "Potato",
    "batata": "Potato",
    # Tomato
    "tomato": "Tomato",
    "tamatar": "Tomato",
    # Mustard
    "mustard": "Mustard",
    "sarson": "Mustard",
    "rai": "Mustard",
    # Gram / Chana
    "gram": "Gram (Chana)",
    "chana": "Gram (Chana)",
    "chhole": "Gram (Chana)",
    "chana dal": "Gram (Chana)",
    # Maize
    "maize": "Maize",
    "makka": "Maize",
    "corn": "Maize",
    "bhutta": "Maize",
    # Soybean
    "soybean": "Soybean",
    "soya": "Soybean",
}

MARKET_ALIASES: dict[str, tuple[str, str]] = {
    "azadpur": ("Azadpur", "NCT of Delhi"),
    "delhi": ("Azadpur", "NCT of Delhi"),
    "ghazipur": ("Ghazipur", "NCT of Delhi"),
    "gazipur": ("Ghazipur", "NCT of Delhi"),
    "okhla": ("Okhla", "NCT of Delhi"),
    "narela": ("Narela", "NCT of Delhi"),
    "khanna": ("Khanna", "Punjab"),
    "lasalgaon": ("Lasalgaon", "Maharashtra"),
    "nasik": ("Lasalgaon", "Maharashtra"),
    "nashik": ("Lasalgaon", "Maharashtra"),
    "indore": ("Indore", "Madhya Pradesh"),
    "karnal": ("Karnal", "Haryana"),
}


@dataclass(frozen=True)
class PriceRecord:
    """Wholesale mandi price record with unit normalization."""

    commodity: str
    market: str
    state: str
    arrival_date: str
    min_price_quintal: int
    max_price_quintal: int
    modal_price_quintal: int

    @property
    def min_price_kg(self) -> float:
        """Normalized minimum price in Rupees per kilogram."""
        return round(self.min_price_quintal / 100.0, 2)

    @property
    def max_price_kg(self) -> float:
        """Normalized maximum price in Rupees per kilogram."""
        return round(self.max_price_quintal / 100.0, 2)

    @property
    def modal_price_kg(self) -> float:
        """Normalized most frequent trading price in Rupees per kilogram."""
        return round(self.modal_price_quintal / 100.0, 2)


@dataclass(frozen=True)
class CommodityTrend:
    """Historical price trend movement."""

    commodity: str
    market: str
    current_modal_kg: float
    previous_modal_kg: float
    change_pct: float
    direction: str  # "up", "down", "steady"


def _clean_token(text: str) -> str:
    cleaned = re.sub(r"[^\w\s]", "", text.lower())
    tokens = [
        t for t in cleaned.split() if t not in {"mandi", "market", "bazar", "price", "bhav", "rate"}
    ]
    return " ".join(tokens).strip()


def resolve_commodity(query: str) -> str:
    """Resolve a colloquial or bilingual commodity name to its canonical name."""
    raw = query.strip()
    if not raw:
        raise InvalidInputError(
            spoken="Please specify an agricultural commodity, such as wheat, onion, or tomato.",
            detail="Commodity query is empty.",
        )

    clean = _clean_token(raw)
    lookup_key = clean if clean else raw.lower()

    if lookup_key in COMMODITY_ALIASES:
        return COMMODITY_ALIASES[lookup_key]

    for key, canonical in COMMODITY_ALIASES.items():
        if lookup_key in key or key in lookup_key:
            return canonical

    matches = difflib.get_close_matches(lookup_key, list(COMMODITY_ALIASES.keys()), n=1, cutoff=0.7)
    if matches:
        return COMMODITY_ALIASES[matches[0]]

    raise InvalidInputError(
        spoken=(
            f"I could not find commodity data for '{raw}'. "
            "Try common crops like wheat, rice, onion, potato, or tomato."
        ),
        detail=f"Commodity '{raw}' not resolved to canonical name.",
    )


def resolve_market(query: str | None) -> tuple[str, str]:
    """Resolve a mandi or market name to canonical name and state."""
    if not query or not query.strip():
        # Default major wholesale market
        return ("Azadpur", "NCT of Delhi")

    raw = query.strip()
    clean = _clean_token(raw)
    lookup_key = clean if clean else raw.lower()

    if lookup_key in MARKET_ALIASES:
        return MARKET_ALIASES[lookup_key]

    for key, target in MARKET_ALIASES.items():
        if lookup_key in key or key in lookup_key:
            return target

    matches = difflib.get_close_matches(lookup_key, list(MARKET_ALIASES.keys()), n=1, cutoff=0.7)
    if matches:
        return MARKET_ALIASES[matches[0]]

    # If unknown market, treat as custom market name in Delhi/National territory
    return (raw.title(), "NCT of Delhi")


def format_price_spoken(
    record: PriceRecord,
    *,
    is_stale: bool = False,
    days_old: int = 0,
) -> str:
    """Format single commodity price into concise speech strictly under 300 characters."""
    kg_price = (
        int(record.modal_price_kg) if record.modal_price_kg.is_integer() else record.modal_price_kg
    )
    spoken = (
        f"{record.commodity} in {record.market} mandi is trading at {record.modal_price_quintal:,} "
        f"rupees per quintal, about {kg_price} rupees per kilogram."
    )

    if days_old > 1 or is_stale:
        day_str = f"{days_old} days ago" if days_old > 1 else "earlier"
        spoken += f" Note: Rates are from {day_str} as markets may have been closed."

    if len(spoken) > 300:
        spoken = spoken[:297] + "..."
    return spoken


def format_comparison_spoken(
    commodity: str,
    records: list[PriceRecord],
    *,
    is_stale: bool = False,
) -> str:
    """Format market comparison into voice output under 300 characters."""
    if not records:
        return f"No comparative price data was found for {commodity} across the requested mandis."

    parts: list[str] = []
    for rec in records[:3]:
        kg_p = int(rec.modal_price_kg) if rec.modal_price_kg.is_integer() else rec.modal_price_kg
        parts.append(f"{rec.market} is {kg_p} rupees per kg")

    joined = ", while ".join(parts)
    spoken = f"{commodity} prices: {joined}."
    if is_stale:
        spoken += " Prices reflect recent trading sessions."

    if len(spoken) > 300:
        spoken = spoken[:297] + "..."
    return spoken


def format_trend_spoken(
    trend: CommodityTrend,
    *,
    is_stale: bool = False,
) -> str:
    """Format price trend into spoken output under 300 characters."""
    curr_kg = (
        int(trend.current_modal_kg)
        if trend.current_modal_kg.is_integer()
        else trend.current_modal_kg
    )

    if trend.direction == "steady":
        spoken = (
            f"{trend.commodity} prices in {trend.market} have stayed steady over the past week, "
            f"holding around {curr_kg} rupees per kg."
        )
    elif trend.direction == "up":
        spoken = (
            f"{trend.commodity} prices in {trend.market} rose by {abs(trend.change_pct):.0f} "
            f"percent over the past week, now at {curr_kg} rupees per kg."
        )
    else:
        spoken = (
            f"{trend.commodity} prices in {trend.market} fell by {abs(trend.change_pct):.0f} "
            f"percent over the past week, down to {curr_kg} rupees per kg."
        )

    if is_stale:
        spoken += " Trend is based on recent market sessions."

    if len(spoken) > 300:
        spoken = spoken[:297] + "..."
    return spoken
