"""Unit and property tests for business ledger domain logic (T10.2)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from hypothesis import given
from hypothesis import strategies as st

from sahayak.modules.business.domain.ledger import (
    compute_customer_balance,
    compute_entry_effect,
    format_add_due_spoken,
    format_customer_balance_spoken,
    format_payment_spoken,
    format_reversal_spoken,
    format_top_dues_spoken,
)


@dataclass
class DummyEntry:
    direction: str
    amount_minor: int


@given(
    entries=st.lists(
        st.tuples(
            st.sampled_from(["debit", "credit"]),
            st.integers(min_value=1, max_value=10_000_000),
        ),
        min_size=0,
        max_size=50,
    )
)
def test_balance_always_equals_sum_of_entries(entries: list[tuple[str, int]]) -> None:
    """Property test: customer balance is mathematically identical to sum of signed effects."""
    ledger_entries = [DummyEntry(direction=d, amount_minor=amt) for d, amt in entries]
    expected_sum = sum(amt if d == "debit" else -amt for d, amt in entries)

    computed = compute_customer_balance(ledger_entries)  # type: ignore[arg-type]
    assert computed == expected_sum


def test_reversal_cancels_entry_effect_exactly() -> None:
    """Reversal entry cancels the original entry effect while maintaining history."""
    # Start with initial due
    initial_entries = [DummyEntry(direction="debit", amount_minor=50000)]
    initial_bal = compute_customer_balance(initial_entries)  # type: ignore[arg-type]
    assert initial_bal == 50000

    # Add mistaken payment of 20000
    payment_entry = DummyEntry(direction="credit", amount_minor=20000)
    entries_with_payment = [*initial_entries, payment_entry]
    bal_after_payment = compute_customer_balance(entries_with_payment)  # type: ignore[arg-type]
    assert bal_after_payment == 30000

    # Reverse the payment (direction becomes debit)
    reversal_entry = DummyEntry(direction="debit", amount_minor=20000)
    entries_after_reversal = [*entries_with_payment, reversal_entry]
    final_bal = compute_customer_balance(entries_after_reversal)  # type: ignore[arg-type]

    # Balance restored to 50000, 3 entries in total
    assert final_bal == initial_bal
    assert len(entries_after_reversal) == 3


def test_spoken_formatters_comply_with_voice_rules() -> None:
    """Voice formatting rules: <= 300 chars, no markdown (*, #, `), natural phrasing."""
    due_spoken = format_add_due_spoken("Ramesh Kumar", 50000, 50000, "INR")
    assert len(due_spoken) <= 300
    assert "*" not in due_spoken
    assert "`" not in due_spoken
    assert "Added due of 500 rupees for Ramesh Kumar" in due_spoken

    payment_spoken = format_payment_spoken("Ramesh Kumar", 50000, 0, "INR")
    assert len(payment_spoken) <= 300
    assert "Recorded payment of 500 rupees from Ramesh Kumar" in payment_spoken
    assert "Balance is zero" in payment_spoken

    bal_pos = format_customer_balance_spoken("Anita", 25000, "INR")
    assert "Anita currently owes 250 rupees" in bal_pos

    bal_zero = format_customer_balance_spoken("Anita", 0, "INR")
    assert "Anita has cleared all dues" in bal_zero

    bal_neg = format_customer_balance_spoken("Anita", -15000, "INR")
    assert "Anita has an advance credit of 150 rupees" in bal_neg

    top_dues_empty = format_top_dues_spoken([], "INR")
    assert "no pending customer dues" in top_dues_empty

    top_dues_populated = format_top_dues_spoken(
        [("Ramesh", 120000), ("Priya", 45000), ("Sunil", 10000)],
        "INR",
        total_customers_with_dues=5,
    )
    assert len(top_dues_populated) <= 300
    assert "Ramesh owes 1200 rupees" in top_dues_populated
    assert "Priya owes 450 rupees" in top_dues_populated

    rev_spoken = format_reversal_spoken("Priya", 25000, "INR")
    assert "Reversed entry for Priya" in rev_spoken


def test_invalid_direction_raises() -> None:
    with pytest.raises(ValueError) as exc:
        compute_entry_effect("invalid", 100)
    assert "Invalid ledger direction" in str(exc.value)
