"""Home and family module satisfying the Module protocol (T9.1)."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select, update

from sahayak.core.db.session import UnitOfWork
from sahayak.core.module import Deps, HealthStatus
from sahayak.modules.home.models import (
    Household,
    HouseholdInvite,
    HouseholdMembership,
    SharedList,
    SharedListItem,
)


class HomeModule:
    """Home and family module providing households tenancy, shared lists, chores, and pantry."""

    def __init__(self) -> None:
        self._deps: Deps | None = None
        self._api: Any = None

    @property
    def name(self) -> str:
        return "home"

    @property
    def version(self) -> str:
        return "0.1.0"

    @property
    def api(self) -> Any:
        if self._api is None:
            if self._deps is None or self._deps.session_factory is None:
                return None
            from sahayak.modules.home.api import HomeAPI

            self._api = HomeAPI(session_factory=self._deps.session_factory)
        return self._api

    def register_tools(self, mcp: Any, deps: Deps) -> None:
        """Register MCP tools for home module."""
        self._deps = deps
        if deps.session_factory is not None:
            from sahayak.modules.home.service.lists import SharedListService
            from sahayak.modules.home.tools.shared_list import set_shared_list_service

            list_service = SharedListService(session_factory=deps.session_factory)
            set_shared_list_service(list_service)

        from sahayak.modules.home.tools.shared_list import (
            SHARED_LIST_DESCRIPTION,
            shared_list,
        )

        tool_decorator = getattr(mcp, "tool", None)
        if callable(tool_decorator):
            tool_decorator(name="shared_list", description=SHARED_LIST_DESCRIPTION)(shared_list)
        elif hasattr(mcp, "add_tool"):
            mcp.add_tool(shared_list, name="shared_list", description=SHARED_LIST_DESCRIPTION)

    def register_jobs(self, worker: Any) -> None:
        """Register background worker jobs for home module."""
        pass

    def migrations_path(self) -> str | None:
        return str(Path(__file__).parent / "migrations")

    def health(self) -> HealthStatus:
        if self._deps is not None and self._deps.session_factory is None:
            return HealthStatus(healthy=False, detail="PostgreSQL session factory missing")
        return HealthStatus(healthy=True, detail="Home module is operational")

    def on_event(self, event: Any) -> None:
        """Dispatched domain events hook."""
        pass

    async def export_user_data(self, user_id: str) -> dict[str, Any]:
        """GDPR Right to Access: export user households, memberships, lists, and items."""
        if self._deps is None or self._deps.session_factory is None:
            return {}

        uid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
        async with UnitOfWork(self._deps.session_factory) as uow:
            res_m = await uow.session.execute(
                select(HouseholdMembership).where(HouseholdMembership.user_id == uid)
            )
            memberships = res_m.scalars().all()
            household_ids = [m.household_id for m in memberships]

            exported_households = []
            exported_lists = []
            exported_items = []
            if household_ids:
                res_h = await uow.session.execute(
                    select(Household).where(Household.id.in_(household_ids))
                )
                exported_households = [h.to_dict() for h in res_h.scalars().all()]

                res_l = await uow.session.execute(
                    select(SharedList).where(SharedList.household_id.in_(household_ids))
                )
                lists = res_l.scalars().all()
                exported_lists = [lst.to_dict() for lst in lists]
                list_ids = [lst.id for lst in lists]
                if list_ids:
                    res_li = await uow.session.execute(
                        select(SharedListItem).where(SharedListItem.list_id.in_(list_ids))
                    )
                    exported_items = [it.to_dict() for it in res_li.scalars().all()]

            res_inv = await uow.session.execute(
                select(HouseholdInvite).where(HouseholdInvite.created_by == uid)
            )
            invites = res_inv.scalars().all()

            return {
                "households": exported_households,
                "memberships": [m.to_dict() for m in memberships],
                "created_invites": [i.to_dict() for i in invites],
                "shared_lists": exported_lists,
                "list_items": exported_items,
            }

    async def delete_user_data(self, user_id: str) -> None:
        """GDPR Right to Erasure: scrub user membership records and handle tenancy ownership."""
        if self._deps is None or self._deps.session_factory is None:
            return

        uid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
        async with UnitOfWork(self._deps.session_factory) as uow:
            # Delete invites created by user
            await uow.session.execute(
                delete(HouseholdInvite).where(HouseholdInvite.created_by == uid)
            )

            # Scrub user references on remaining list items
            await uow.session.execute(
                update(SharedListItem).where(SharedListItem.added_by == uid).values(added_by=None)
            )

            # Check memberships to manage household ownership
            res_m = await uow.session.execute(
                select(HouseholdMembership).where(HouseholdMembership.user_id == uid)
            )
            user_memberships = list(res_m.scalars().all())

            for m in user_memberships:
                all_members_res = await uow.session.execute(
                    select(HouseholdMembership).where(
                        HouseholdMembership.household_id == m.household_id
                    )
                )
                all_members = list(all_members_res.scalars().all())
                other_members = [om for om in all_members if om.user_id != uid]

                if not other_members:
                    # Sole member: delete entire household (cascades)
                    await uow.session.execute(
                        delete(Household).where(Household.id == m.household_id)
                    )
                else:
                    if m.role == "owner":
                        # Transfer ownership to oldest member
                        earliest = sorted(other_members, key=lambda x: x.joined_at)[0]
                        earliest.role = "owner"
                    await uow.session.execute(
                        delete(HouseholdMembership).where(
                            HouseholdMembership.household_id == m.household_id,
                            HouseholdMembership.user_id == uid,
                        )
                    )


module = HomeModule()
