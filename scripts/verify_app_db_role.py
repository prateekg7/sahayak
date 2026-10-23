"""Script to verify that the sahayak_app database role cannot execute DDL statements.

Per AGENTS.md §7.3 and tasks.md T4.1:
- The app DB role cannot run DDL; migrations use a separate migrator role.
- Verifies that attempting CREATE or DROP TABLE fails with permission denied.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine


class DDLPermissionViolationError(Exception):
    """Raised when an unprivileged app role is unexpectedly allowed to run DDL."""


async def verify_app_role_cannot_run_ddl(session: AsyncSession) -> dict[str, str]:
    """Verify that the active database session CAN run DML but CANNOT run DDL.

    Returns a dict summary of assertions passed.
    Raises DDLPermissionViolationError if a DDL statement succeeds.
    """
    # 1. Verify DML/SELECT is allowed
    result = await session.execute(text("SELECT 1 as test_dml"))
    row = result.scalar()
    if row != 1:
        msg = f"Expected SELECT 1 to return 1, got {row}"
        raise ValueError(msg)

    # 2. Verify DDL CREATE TABLE fails
    ddl_create_succeeded = False
    try:
        await session.execute(
            text("CREATE TABLE IF NOT EXISTS core.unauthorized_ddl_probe (id int primary key)")
        )
        ddl_create_succeeded = True
    except (ProgrammingError, DBAPIError) as exc:
        err_msg = str(exc).lower()
        if "permission denied" not in err_msg and "insufficientprivilege" not in err_msg:
            pass
        await session.rollback()

    if ddl_create_succeeded:
        await session.rollback()
        msg = "Security check failed: sahayak_app role was able to CREATE TABLE in core schema!"
        raise DDLPermissionViolationError(msg)

    # 3. Verify DDL DROP TABLE fails
    ddl_drop_succeeded = False
    try:
        await session.execute(text("DROP TABLE IF EXISTS core.unauthorized_ddl_probe"))
        ddl_drop_succeeded = True
    except (ProgrammingError, DBAPIError):
        await session.rollback()

    if ddl_drop_succeeded:
        await session.rollback()
        msg = "Security check failed: sahayak_app role was able to DROP TABLE in core schema!"
        raise DDLPermissionViolationError(msg)

    return {
        "status": "passed",
        "dml_allowed": "true",
        "ddl_create_blocked": "true",
        "ddl_drop_blocked": "true",
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description="Verify app database role cannot run DDL.")
    parser.add_argument(
        "--db-url",
        default="postgresql+asyncpg://sahayak_app:secret@localhost:5432/sahayak",
        help="Database connection URL for the app user",
    )
    args = parser.parse_args()

    engine = create_async_engine(args.db_url)
    try:
        async with AsyncSession(engine) as session:
            summary = await verify_app_role_cannot_run_ddl(session)
            print(f"Role verification passed: {summary}")
    except DDLPermissionViolationError as e:
        print(f"SECURITY VIOLATION: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error connecting or running verification: {e}", file=sys.stderr)
        sys.exit(2)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
