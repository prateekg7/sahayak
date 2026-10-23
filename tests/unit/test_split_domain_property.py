"""Hypothesis property tests for split_bill algorithms (T6.3).

Verifies two invariants:
1. Shares always sum exactly to the total minor units (no lost or gained paisa/cent).
2. Group balances net to zero across all expenses and settlements.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from sahayak.modules.finance.domain.split import (
    calculate_group_balances,
    calculate_minimal_settlements,
    split_by_shares,
    split_equally,
)


@given(
    total_minor=st.integers(min_value=1, max_value=10_000_000_00),  # up to 10 crore minor units
    num_participants=st.integers(min_value=1, max_value=50),
)
def test_split_equally_sums_to_total_invariant(total_minor: int, num_participants: int) -> None:
    """Invariant: sum of all shares must equal total_minor down to the last paisa."""
    participants = [f"User_{i}" for i in range(num_participants)]
    shares = split_equally(total_minor, participants)

    assert len(shares) == num_participants
    share_sum = sum(s.amount_minor for s in shares)
    assert share_sum == total_minor, (
        f"Equal split lost/gained money: expected {total_minor}, got {share_sum}"
    )

    # Any two shares can differ by at most 1 minor unit
    amounts = [s.amount_minor for s in shares]
    assert max(amounts) - min(amounts) in (0, 1)


@given(
    total_minor=st.integers(min_value=1, max_value=10_000_000_00),
    weights=st.lists(st.integers(min_value=1, max_value=100), min_size=1, max_size=20),
)
def test_split_by_shares_sums_to_total_invariant(total_minor: int, weights: list[int]) -> None:
    """Invariant: Hamilton-Hare largest-remainder method preserves exact total."""
    participants_with_weights = [(f"User_{i}", w) for i, w in enumerate(weights)]
    shares = split_by_shares(total_minor, participants_with_weights)

    share_sum = sum(s.amount_minor for s in shares)
    assert share_sum == total_minor, (
        f"Weighted split lost/gained money: expected {total_minor}, got {share_sum}"
    )


@given(
    num_members=st.integers(min_value=2, max_value=10),
    num_expenses=st.integers(min_value=1, max_value=15),
    seed_amounts=st.lists(st.integers(min_value=100, max_value=100_000), min_size=1, max_size=15),
)
def test_group_balances_net_to_zero_invariant(
    num_members: int, num_expenses: int, seed_amounts: list[int]
) -> None:
    """Invariant: Across any group, the sum of all net balances must equal zero."""
    members = [f"Member_{i}" for i in range(num_members)]

    expenses = []
    for i in range(min(num_expenses, len(seed_amounts))):
        amt = seed_amounts[i]
        payer = members[i % num_members]
        shares = split_equally(amt, members)
        split_map = {s.name: s.amount_minor for s in shares}
        expenses.append((payer, amt, split_map))

    balances = calculate_group_balances(members, expenses, settlements=[])
    net_sum = sum(b.net_minor for b in balances)
    assert net_sum == 0, f"Group balances do not net to zero: sum={net_sum}"

    # Minimal settlements should resolve all balances
    transfers = calculate_minimal_settlements(balances)
    settlements = [(t.from_name, t.to_name, t.amount_minor) for t in transfers]

    balances_after_settlement = calculate_group_balances(members, expenses, settlements)
    for b in balances_after_settlement:
        assert b.net_minor == 0, f"Balance for {b.name} after settlement is not zero: {b.net_minor}"
