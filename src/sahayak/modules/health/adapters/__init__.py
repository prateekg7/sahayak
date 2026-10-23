"""Repository adapters for the health module."""

from __future__ import annotations

from sahayak.modules.health.adapters.entries import SQLAlchemyHealthRepository

__all__ = ["SQLAlchemyHealthRepository"]
