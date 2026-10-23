"""Category normalization for personal expenses (T6.1)."""

from __future__ import annotations

import re

CATEGORY_KEYWORDS = {
    "groceries": [
        "grocery",
        "groceries",
        "milk",
        "vegetable",
        "vegetables",
        "veggies",
        "supermarket",
        "bread",
        "eggs",
        "fruits",
    ],
    "food": [
        "food",
        "dinner",
        "lunch",
        "breakfast",
        "meal",
        "coffee",
        "cafe",
        "restaurant",
        "swiggy",
        "zomato",
        "snack",
        "pizza",
        "burger",
    ],
    "transport": [
        "transport",
        "cab",
        "taxi",
        "uber",
        "ola",
        "auto",
        "metro",
        "bus",
        "train",
        "flight",
        "petrol",
        "diesel",
        "fuel",
        "toll",
        "parking",
    ],
    "utilities": [
        "utilities",
        "utility",
        "electricity",
        "power",
        "water",
        "wifi",
        "internet",
        "broadband",
        "phone",
        "mobile",
        "recharge",
    ],
    "entertainment": [
        "entertainment",
        "movie",
        "cinema",
        "netflix",
        "prime",
        "hotstar",
        "spotify",
        "concert",
        "game",
        "party",
    ],
    "healthcare": [
        "healthcare",
        "health",
        "doctor",
        "medicine",
        "pharmacy",
        "hospital",
        "clinic",
        "dental",
        "test",
    ],
    "shopping": [
        "shopping",
        "clothes",
        "clothing",
        "shoes",
        "dress",
        "amazon",
        "flipkart",
        "mall",
    ],
    "education": [
        "education",
        "books",
        "book",
        "course",
        "tuition",
        "exam",
        "school",
        "college",
    ],
}


def normalize_category(category: str | None, note: str | None = None) -> str:
    """Normalize raw voice input or notes into standard expense categories."""
    haystack = f"{category or ''} {note or ''}".strip().lower()
    if not haystack:
        return "other"

    # Match predefined keyword dictionary
    for cat_name, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in haystack:
                return cat_name

    # If user provided a short, clean custom category
    if category:
        clean = category.strip().lower()
        if re.match(r"^[a-z0-9_-]{1,32}$", clean):
            return clean

    return "other"
