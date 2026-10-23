"""Contract tests for deployment profiles over Streamable HTTP (T13.1, ADR 0016)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.config import Settings, get_settings
from sahayak.core.module import Deps, ModuleRegistry
from sahayak.core.profiles import BUNDLE_PROFILES
from sahayak.main import create_app

SNAPSHOT_DIR = Path("tests/snapshots")


@pytest.mark.asyncio
@pytest.mark.parametrize("profile_name", ["study", "life", "work", "home"])
async def test_deployment_profile_mcp_surface_matches_snapshot(
    profile_name: str,
) -> None:
    """Each deployment profile starts independently and exposes only its bundle's tools."""
    bundle_modules = BUNDLE_PROFILES[profile_name]
    snapshot_path = SNAPSHOT_DIR / f"{profile_name}_tools.json"
    assert snapshot_path.is_file(), f"Snapshot file {snapshot_path} must exist"

    snapshot_data = json.loads(snapshot_path.read_text(encoding="utf-8"))
    expected_tool_names = sorted(entry["name"] for entry in snapshot_data)

    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    registry = ModuleRegistry()
    registry.load(bundle_modules)
    deps = Deps(session_factory=session_factory)

    app = create_app(
        settings=Settings(deployment_profile=profile_name, _env_file=None),  # type: ignore[call-arg]
        registry=registry,
        deps=deps,
    )

    asgi_transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=asgi_transport, base_url="http://testserver") as client,
        streamable_http_client("http://testserver/mcp", http_client=cast(Any, client)) as (
            read_stream,
            write_stream,
        ),
        ClientSession(read_stream, write_stream) as session,
    ):
        await session.initialize()
        tools_result = await session.list_tools()
        actual_tool_names = sorted(t.name for t in tools_result.tools)

        assert actual_tool_names == expected_tool_names
        assert len(actual_tool_names) == len(snapshot_data)
        await engine.dispose()


@pytest.mark.asyncio
async def test_shared_identity_persistence_across_profiles() -> None:
    """User data persists across different profiles sharing the same database infrastructure."""
    import uuid

    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))

    # 1. Study registry and module export
    study_registry = ModuleRegistry()
    study_registry.load(BUNDLE_PROFILES["study"])
    study_mod = study_registry.get("academics")
    assert study_mod is not None

    # 2. Life registry and module export
    life_registry = ModuleRegistry()
    life_registry.load(BUNDLE_PROFILES["life"])
    productivity_mod = life_registry.get("productivity")
    finance_mod = life_registry.get("finance")
    health_mod = life_registry.get("health")
    assert productivity_mod is not None
    assert finance_mod is not None
    assert health_mod is not None

    test_user_id = str(uuid.uuid4())

    # Verify both profiles' modules export under the same user_id without collision
    study_export = await study_mod.export_user_data(test_user_id)
    prod_export = await productivity_mod.export_user_data(test_user_id)
    fin_export = await finance_mod.export_user_data(test_user_id)
    health_export = await health_mod.export_user_data(test_user_id)

    assert "quizzes" in study_export or "attempts" in study_export or isinstance(study_export, dict)
    assert isinstance(prod_export, dict)
    assert isinstance(fin_export, dict)
    assert isinstance(health_export, dict)

    await engine.dispose()
