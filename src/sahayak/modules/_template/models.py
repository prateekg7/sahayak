"""SQLAlchemy models for the template module."""

from __future__ import annotations

from sqlalchemy import MetaData, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

metadata = MetaData(schema="_template")


class TemplateBase(DeclarativeBase):
    """Base for models owned by the _template module."""

    metadata = metadata


class PingAudit(TemplateBase):
    """Audit record of a ping call."""

    __tablename__ = "ping_audits"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    message: Mapped[str] = mapped_column(String(256), nullable=False)
