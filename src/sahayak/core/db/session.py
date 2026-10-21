"""Async SQLAlchemy engine construction and transactional unit of work."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from sahayak.core.config import Settings

SessionFactory = Callable[[], AsyncSession]


def create_engine(settings: Settings) -> AsyncEngine:
    """Create an async PostgreSQL engine from validated configuration."""
    return create_async_engine(str(settings.database_url), pool_pre_ping=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create non-expiring sessions bound to an application engine."""
    return async_sessionmaker(engine, expire_on_commit=False)


class UnitOfWork:
    """Scope one database session and transaction to an application operation."""

    def __init__(self, session_factory: SessionFactory) -> None:
        """Store the injected session factory."""
        self._session_factory = session_factory
        self._session: AsyncSession | None = None

    @property
    def session(self) -> AsyncSession:
        """Return the active session.

        Raises:
            RuntimeError: If called outside the unit-of-work context.
        """
        if self._session is None:
            msg = "UnitOfWork session is available only inside its context"
            raise RuntimeError(msg)
        return self._session

    async def __aenter__(self) -> UnitOfWork:
        """Open a session for the current unit of work."""
        self._session = self._session_factory()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        _exc_value: BaseException | None,
        _traceback: object | None,
    ) -> None:
        """Commit successful work, roll back failures, and always close the session."""
        if self._session is None:
            return
        try:
            if exc_type is None:
                await self._session.commit()
            else:
                await self._session.rollback()
        finally:
            await self._session.close()
            self._session = None
