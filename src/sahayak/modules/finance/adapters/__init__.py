"""SQLAlchemy database adapters for the finance module."""

from __future__ import annotations

from sahayak.modules.finance.adapters.expenses import SQLAlchemyExpenseRepository

__all__ = ["SQLAlchemyExpenseRepository"]
