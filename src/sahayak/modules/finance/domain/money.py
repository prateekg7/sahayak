"""Money value object, exact integer minor unit calculations, and voice speech formatting (T6.1).

Per PRD §1.2 Rule 4:
Never use floating-point for money. Integer minor units + ISO currency code.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from sahayak.core.errors import InvalidInputError

CURRENCY_SYMBOLS = {
    "INR": "₹",
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
}

MAX_EXPENSE_MINOR = 1_000_000_000  # 10 million major units max safeguard


@dataclass(frozen=True)
class Money:
    """Exact integer representation of a monetary value in minor units."""

    amount_minor: int
    currency: str = "INR"

    def __post_init__(self) -> None:
        if not isinstance(self.amount_minor, int):
            raise TypeError("amount_minor must be an integer, never float")


def parse_to_minor_units(amount: int | str | None, currency: str = "INR") -> int:
    """Safely convert a user or Alexa-supplied amount into integer minor units.

    Uses decimal.Decimal strictly; floats are never used.
    """
    if amount is None:
        raise InvalidInputError("Amount is required")

    cleaned = str(amount).strip()
    # Strip common currency signs and whitespace
    cleaned = re.sub(r"[₹$€£,\s]", "", cleaned)
    if not cleaned:
        raise InvalidInputError("Amount cannot be empty")

    try:
        dec = Decimal(cleaned)
    except InvalidOperation as err:
        raise InvalidInputError(f"Invalid monetary amount '{amount}'") from err

    if dec <= 0:
        raise InvalidInputError("Amount must be greater than zero")

    # Minor units: multiply by 100 with exact rounding to nearest integer
    minor = int((dec * 100).quantize(Decimal("1")))
    if minor > MAX_EXPENSE_MINOR:
        raise InvalidInputError("Amount exceeds maximum transaction limit")

    return minor


def format_money_spoken(amount_minor: int, currency: str = "INR") -> str:
    """Format money for natural voice synthesis without symbols."""
    curr = currency.upper().strip()
    major = amount_minor // 100
    minor = amount_minor % 100

    if curr == "INR":
        unit = "rupee" if major == 1 else "rupees"
        if minor == 0:
            return f"{major} {unit}"
        if major == 0:
            return f"{minor} paise"
        return f"{major} {unit} and {minor} paise"

    if curr == "USD":
        unit = "dollar" if major == 1 else "dollars"
        sub_unit = "cent" if minor == 1 else "cents"
        if minor == 0:
            return f"{major} {unit}"
        if major == 0:
            return f"{minor} {sub_unit}"
        return f"{major} {unit} and {minor} {sub_unit}"

    if curr == "EUR":
        unit = "euro" if major == 1 else "euros"
        sub_unit = "cent" if minor == 1 else "cents"
        if minor == 0:
            return f"{major} {unit}"
        return f"{major} {unit} and {minor} {sub_unit}"

    # Generic ISO fallback
    if minor == 0:
        return f"{major} {curr}"
    return f"{major} {curr} and {minor} minor units"


def format_money_display(amount_minor: int, currency: str = "INR") -> str:
    """Format money for visual display in payload data."""
    curr = currency.upper().strip()
    symbol = CURRENCY_SYMBOLS.get(curr, f"{curr} ")
    major = amount_minor // 100
    minor = amount_minor % 100
    return f"{symbol}{major}.{minor:02d}"
