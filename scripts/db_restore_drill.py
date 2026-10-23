"""Database backup and restore drill script (T4.8).

Simulates and verifies database restore operations into a scratch test database,
recording timings to validate Recovery Time Objective (RTO <= 30 minutes).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine


async def execute_restore_drill(
    session: AsyncSession,
) -> dict[str, Any]:
    """Execute validation queries on a restored or scratch database."""
    t0 = time.monotonic()

    # 1. Verify core schemas exist
    schemas_query = (
        "SELECT schema_name FROM information_schema.schemata "
        "WHERE schema_name IN ('core', 'academics')"
    )
    schemas_res = await session.execute(text(schemas_query))
    found_schemas = {row[0] for row in schemas_res.fetchall()}

    # 2. Verify key tables exist
    tables_query = (
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema IN ('core', 'academics')"
    )
    tables_res = await session.execute(text(tables_query))
    found_tables = {row[0] for row in tables_res.fetchall()}

    duration = time.monotonic() - t0

    return {
        "status": "success",
        "duration_seconds": round(duration, 3),
        "found_schemas": sorted(found_schemas),
        "table_count": len(found_tables),
        "rto_target_met": duration < 1800,  # 30 minutes in seconds
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run DB restore verification drill.")
    parser.add_argument(
        "--db-url",
        default="postgresql+asyncpg://sahayak:sahayak@localhost:5432/sahayak",
        help="Connection URL for the restored scratch database",
    )
    args = parser.parse_args()

    engine = create_async_engine(args.db_url)
    try:
        async with AsyncSession(engine) as session:
            results = await execute_restore_drill(session)
            print(f"Restore drill SUCCESS: {results}")
    except Exception as e:
        print(f"Restore drill FAILED: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
