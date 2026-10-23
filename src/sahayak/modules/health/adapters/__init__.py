"""Health module adapters."""

from sahayak.modules.health.adapters.entries import SQLAlchemyHealthRepository
from sahayak.modules.health.adapters.medicines import SQLAlchemyMedicineRepository

__all__ = ["SQLAlchemyHealthRepository", "SQLAlchemyMedicineRepository"]
