"""Domain algorithms for bill splitting, largest-remainder rounding, and balance settlements (T6.3).

Rule 4: Zero floating-point representation for money. Integer minor units strictly preserved.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sahayak.core.errors import InvalidInputError
from sahayak.modules.finance.domain.money import format_money_spoken


@dataclass(frozen=True)
class ParticipantShare:
    """Calculated financial share for a participant."""

    name: str
    amount_minor: int


@dataclass(frozen=True)
class NetBalance:
    """Net credit or debit balance for a participant."""

    name: str
    net_minor: int  # Positive means they are owed money; negative means they owe money


@dataclass(frozen=True)
class SettlementTransfer:
    """Recommended minimal cash transfer to settle group debts."""

    from_name: str
    to_name: str
    amount_minor: int


def split_equally(total_minor: int, participants: Sequence[str]) -> list[ParticipantShare]:
    """Split total_minor equally among participants using the largest-remainder method.

    Guarantees:
    1. sum(shares) == total_minor exactly (no lost or gained paisa/cent).
    2. Any participant's share differs from any other by at most 1 minor unit.
    """
    if total_minor <= 0:
        raise InvalidInputError("Total amount must be greater than zero.")

    clean_names = [p.strip() for p in participants if p.strip()]
    if not clean_names:
        raise InvalidInputError("At least one participant is required to split a bill.")

    n = len(clean_names)
    base_share = total_minor // n
    remainder = total_minor % n

    shares: list[ParticipantShare] = []
    for i, name in enumerate(clean_names):
        # Distribute remaining minor units one by one to the first 'remainder' participants
        share = base_share + (1 if i < remainder else 0)
        shares.append(ParticipantShare(name=name, amount_minor=share))

    return shares


def split_by_shares(
    total_minor: int,
    participants_with_weights: Sequence[tuple[str, int]],
) -> list[ParticipantShare]:
    """Split total_minor proportional to integer weights using Hamilton-Hare method.

    Guarantees: sum(shares) == total_minor exactly.
    """
    if total_minor <= 0:
        raise InvalidInputError("Total amount must be greater than zero.")

    valid_pairs = [(name.strip(), w) for name, w in participants_with_weights if name.strip()]
    if not valid_pairs:
        raise InvalidInputError("Participants and positive weights required.")

    total_weight = sum(w for _, w in valid_pairs)
    if total_weight <= 0:
        raise InvalidInputError("Total weight must be greater than zero.")

    # Calculate exact rational shares and integer floor shares
    floors: list[int] = []
    remainders: list[tuple[Decimal, int]] = []  # (fractional remainder, index)

    total_dec = Decimal(total_minor)
    weight_sum_dec = Decimal(total_weight)

    for idx, (_, weight) in enumerate(valid_pairs):
        exact_share = (total_dec * Decimal(weight)) / weight_sum_dec
        fl = int(exact_share)
        frac = exact_share - Decimal(fl)
        floors.append(fl)
        remainders.append((frac, idx))

    # How many remainder units need to be allocated?
    allocated = sum(floors)
    shortfall = total_minor - allocated

    # Sort descending by fractional remainder
    remainders.sort(key=lambda item: item[0], reverse=True)

    final_shares = list(floors)
    for k in range(shortfall):
        winner_idx = remainders[k][1]
        final_shares[winner_idx] += 1

    return [
        ParticipantShare(name=valid_pairs[i][0], amount_minor=final_shares[i])
        for i in range(len(valid_pairs))
    ]


def calculate_group_balances(
    members: Sequence[str],
    expenses: Sequence[tuple[str, int, dict[str, int]]],  # (payer, total_minor, split_map)
    settlements: Sequence[tuple[str, str, int]],  # (from_name, to_name, amount_minor)
) -> list[NetBalance]:
    """Calculate net balance for each group member across all expenses and settlements.

    Guarantees: sum(net_balances) == 0 across the group.
    """
    balance_map: dict[str, int] = {m.strip(): 0 for m in members if m.strip()}

    for payer, _total, split_map in expenses:
        payer_clean = payer.strip()
        for debtor, share in split_map.items():
            debtor_clean = debtor.strip()
            if payer_clean == debtor_clean:
                continue  # Paying for oneself does not create debt
            balance_map[payer_clean] = balance_map.get(payer_clean, 0) + share
            balance_map[debtor_clean] = balance_map.get(debtor_clean, 0) - share

    for from_p, to_p, amount in settlements:
        from_clean = from_p.strip()
        to_clean = to_p.strip()
        balance_map[from_clean] = balance_map.get(from_clean, 0) + amount
        balance_map[to_clean] = balance_map.get(to_clean, 0) - amount

    return [NetBalance(name=name, net_minor=net) for name, net in balance_map.items()]


def calculate_minimal_settlements(balances: Sequence[NetBalance]) -> list[SettlementTransfer]:
    """Compute optimal minimal cash transfers to settle all group debts."""
    debtors: list[list[Any]] = []  # [-balance, name]
    creditors: list[list[Any]] = []  # [balance, name]

    for b in balances:
        if b.net_minor < 0:
            debtors.append([-b.net_minor, b.name])
        elif b.net_minor > 0:
            creditors.append([b.net_minor, b.name])

    # Greedy settlement matching largest debtor with largest creditor
    transfers: list[SettlementTransfer] = []

    while debtors and creditors:
        debtors.sort(key=lambda x: x[0], reverse=True)
        creditors.sort(key=lambda x: x[0], reverse=True)

        debt_amt, debtor_name = debtors[0]
        cred_amt, creditor_name = creditors[0]

        transfer_amt = min(debt_amt, cred_amt)
        transfers.append(
            SettlementTransfer(
                from_name=debtor_name,
                to_name=creditor_name,
                amount_minor=transfer_amt,
            )
        )

        debtors[0][0] -= transfer_amt
        creditors[0][0] -= transfer_amt

        if debtors[0][0] == 0:
            debtors.pop(0)
        if creditors[0][0] == 0:
            creditors.pop(0)

    return transfers


def format_split_spoken(
    total_minor: int,
    currency: str,
    payer: str,
    shares: list[ParticipantShare],
) -> str:
    """Generate spoken summary for a split bill."""
    total_str = format_money_spoken(total_minor, currency)
    n = len(shares)
    clean_payer = payer.strip().lower()

    other_shares = [s for s in shares if s.name.strip().lower() != clean_payer]
    if not other_shares:
        return f"Split {total_str} for yourself."

    parts = [
        f"{s.name} owes {format_money_spoken(s.amount_minor, currency)}" for s in other_shares[:4]
    ]
    return f"Split {total_str} among {n} people. {', and '.join(parts)}."


def format_balances_spoken(
    group_name: str, currency: str, transfers: list[SettlementTransfer]
) -> str:
    """Generate spoken report on outstanding debts in a group."""
    if not transfers:
        return f"All balances in {group_name} are settled."

    parts = [
        f"{t.from_name} owes {t.to_name} {format_money_spoken(t.amount_minor, currency)}"
        for t in transfers[:3]
    ]
    return f"In {group_name}, {', and '.join(parts)}."


def format_settlement_spoken(from_name: str, to_name: str, amount_minor: int, currency: str) -> str:
    """Generate spoken confirmation of recorded settlement."""
    amt_str = format_money_spoken(amount_minor, currency)
    return f"Recorded settlement of {amt_str} from {from_name} to {to_name}."
