"""Domain logic for business ledger, customer dues, and speech formatting (T10.2)."""

from __future__ import annotations

from typing import Protocol

from sahayak.modules.business.domain.orders import format_currency_spoken


class LedgerEntryLike(Protocol):
    """Protocol for ledger entry records."""

    direction: str
    amount_minor: int


def compute_entry_effect(direction: str, amount_minor: int) -> int:
    """Compute the net signed balance effect of a ledger entry.

    Debits (customer taking goods on credit / dues) increase the debt owed (+).
    Credits (customer paying down dues) reduce the debt owed (-).
    """
    if direction == "debit":
        return amount_minor
    elif direction == "credit":
        return -amount_minor
    raise ValueError(f"Invalid ledger direction: {direction}")


def compute_customer_balance(entries: list[LedgerEntryLike]) -> int:
    """Compute total outstanding balance owed by customer from ledger entries.

    Positive balance = customer owes money (debt).
    Zero = all dues settled.
    Negative balance = customer has advance store credit.
    """
    return sum(compute_entry_effect(e.direction, e.amount_minor) for e in entries)


def format_balance_phrase(balance_minor: int, currency: str = "INR") -> str:
    """Format a customer balance into a clean, natural spoken voice phrase."""
    if balance_minor > 0:
        return f"Current balance is {format_currency_spoken(balance_minor, currency)}"
    elif balance_minor == 0:
        return "Balance is zero"
    else:
        abs_balance = abs(balance_minor)
        return f"Advance credit is {format_currency_spoken(abs_balance, currency)}"


def format_add_due_spoken(
    customer_name: str,
    amount_minor: int,
    new_balance_minor: int,
    currency: str = "INR",
) -> str:
    """Voice summary for recording a customer due."""
    amt_str = format_currency_spoken(amount_minor, currency)
    bal_phrase = format_balance_phrase(new_balance_minor, currency)
    text = f"Added due of {amt_str} for {customer_name}. {bal_phrase}."
    return text[:300]


def format_payment_spoken(
    customer_name: str,
    amount_minor: int,
    new_balance_minor: int,
    currency: str = "INR",
) -> str:
    """Voice summary for recording a customer payment."""
    amt_str = format_currency_spoken(amount_minor, currency)
    bal_phrase = format_balance_phrase(new_balance_minor, currency)
    text = f"Recorded payment of {amt_str} from {customer_name}. {bal_phrase}."
    return text[:300]


def format_customer_balance_spoken(
    customer_name: str,
    balance_minor: int,
    currency: str = "INR",
) -> str:
    """Voice summary for querying a single customer balance."""
    if balance_minor > 0:
        amt_str = format_currency_spoken(balance_minor, currency)
        text = f"{customer_name} currently owes {amt_str}."
    elif balance_minor == 0:
        text = f"{customer_name} has cleared all dues. Balance is zero."
    else:
        abs_amt_str = format_currency_spoken(abs(balance_minor), currency)
        text = f"{customer_name} has an advance credit of {abs_amt_str}."
    return text[:300]


def format_top_dues_spoken(
    dues: list[tuple[str, int]],
    currency: str = "INR",
    total_customers_with_dues: int | None = None,
) -> str:
    """Voice summary listing customers with top outstanding dues."""
    if not dues:
        return "There are no pending customer dues."

    items_spoken = [
        f"{name} owes {format_currency_spoken(balance, currency)}" for name, balance in dues[:5]
    ]
    summary = "Top dues: " + ", ".join(items_spoken) + "."
    if total_customers_with_dues is not None and total_customers_with_dues > len(dues[:5]):
        remaining = total_customers_with_dues - len(dues[:5])
        summary += f" Plus {remaining} more customers with dues."
    return summary[:300]


def format_reversal_spoken(
    customer_name: str,
    new_balance_minor: int,
    currency: str = "INR",
) -> str:
    """Voice summary for reversing a ledger entry."""
    bal_phrase = format_balance_phrase(new_balance_minor, currency)
    text = f"Reversed entry for {customer_name}. {bal_phrase}."
    return text[:300]
