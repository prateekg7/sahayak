"""Application service orchestrating bill splitting, balances, and settlements (T6.3)."""

from __future__ import annotations

import uuid
from typing import Any

from sahayak.core.db.session import UnitOfWork
from sahayak.core.errors import InvalidInputError, NotFoundError
from sahayak.modules.finance.adapters.split_bill import SQLAlchemySplitBillRepository
from sahayak.modules.finance.domain.money import (
    format_money_display,
    parse_to_minor_units,
)
from sahayak.modules.finance.domain.split import (
    calculate_group_balances,
    calculate_minimal_settlements,
    format_balances_spoken,
    format_settlement_spoken,
    format_split_spoken,
    split_equally,
)
from sahayak.modules.finance.schemas import (
    GroupSummaryData,
    NetBalanceData,
    ParticipantShareData,
    SettlementTransferData,
    SplitBillRequest,
    SplitBillResponseData,
)


class SplitBillService:
    """Service orchestrating bill splitting, group balances, and debt settlements."""

    def __init__(self, session_factory: Any) -> None:
        self.session_factory = session_factory

    async def execute(
        self,
        user_id: uuid.UUID,
        request: SplitBillRequest,
    ) -> tuple[SplitBillResponseData, str]:
        """Dispatch split bill action."""
        action = request.action.value if hasattr(request.action, "value") else str(request.action)

        if action == "split":
            return await self._handle_split(user_id, request)
        if action == "balances":
            return await self._handle_balances(user_id, request)
        if action == "settle":
            return await self._handle_settle(user_id, request)
        if action == "create_group":
            return await self._handle_create_group(user_id, request)
        if action == "list_groups":
            return await self._handle_list_groups(user_id, request)

        raise InvalidInputError(f"Unsupported split bill action: {action}")

    def _parse_participants(self, raw: list[str] | str | None, payer: str) -> list[str]:
        names: list[str] = []
        if isinstance(raw, list):
            names = [p.strip() for p in raw if p.strip()]
        elif isinstance(raw, str):
            names = [p.strip() for p in raw.split(",") if p.strip()]

        clean_payer = payer.strip() if payer else "You"
        # Ensure payer is present
        payer_present = any(n.lower() == clean_payer.lower() for n in names)
        if not payer_present and clean_payer:
            names.insert(0, clean_payer)

        if len(names) < 2:
            raise InvalidInputError(
                "At least two participants are required to split a bill. "
                "Specify participants like 'Alice, Bob, Charlie'."
            )
        return names

    async def _handle_split(
        self,
        user_id: uuid.UUID,
        request: SplitBillRequest,
    ) -> tuple[SplitBillResponseData, str]:
        """Split a bill among participants and persist if attached to a group."""
        if request.amount is None:
            raise InvalidInputError("Please specify a bill amount to split.")

        amount_minor = parse_to_minor_units(request.amount, request.currency)
        currency = (request.currency or "INR").upper().strip()
        payer = (request.payer or "You").strip()

        participants = self._parse_participants(request.participants, payer)
        shares = split_equally(amount_minor, participants)

        group_name = request.group.strip() if request.group else None
        split_map = {s.name: s.amount_minor for s in shares}

        if group_name:
            async with UnitOfWork(self.session_factory) as uow:
                repo = SQLAlchemySplitBillRepository(uow.session)
                group = await repo.get_group_by_name(user_id, group_name)
                if group is None:
                    group = await repo.create_group(
                        user_id=user_id,
                        name=group_name,
                        currency=currency,
                        members=participants,
                    )
                else:
                    await repo.add_group_members(group.id, participants)

                desc = request.description or "Shared Bill"
                await repo.create_shared_expense(
                    group_id=group.id,
                    payer_name=payer,
                    total_minor=amount_minor,
                    description=desc,
                    split_data=split_map,
                )

        spoken = format_split_spoken(amount_minor, currency, payer, shares)
        share_data = [
            ParticipantShareData(
                name=s.name,
                amount_minor=s.amount_minor,
                formatted_amount=format_money_display(s.amount_minor, currency),
            )
            for s in shares
        ]

        return (
            SplitBillResponseData(
                action="split",
                group_name=group_name,
                total_minor=amount_minor,
                currency=currency,
                shares=share_data,
                count=len(share_data),
            ),
            spoken,
        )

    async def _handle_balances(
        self,
        user_id: uuid.UUID,
        request: SplitBillRequest,
    ) -> tuple[SplitBillResponseData, str]:
        """Calculate outstanding debts and optimal settlement plan for a group."""
        if not request.group or not request.group.strip():
            raise InvalidInputError("Please specify a group name to check balances.")

        group_name = request.group.strip()
        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemySplitBillRepository(uow.session)
            group = await repo.get_group_by_name(user_id, group_name)
            if group is None:
                raise NotFoundError(f"No group found with name '{group_name}'.")

            members_models = await repo.get_group_members(group.id)
            member_names = [m.name for m in members_models]

            expenses_models = await repo.list_shared_expenses(group.id)
            expenses_data = [(e.payer_name, e.total_minor, e.split_data) for e in expenses_models]

            settlements_models = await repo.list_settlements(group.id)
            settlements_data = [
                (s.from_name, s.to_name, s.amount_minor) for s in settlements_models
            ]

        balances = calculate_group_balances(member_names, expenses_data, settlements_data)
        transfers = calculate_minimal_settlements(balances)

        spoken = format_balances_spoken(group.name, group.currency, transfers)

        balance_data = [
            NetBalanceData(
                name=b.name,
                net_minor=b.net_minor,
                formatted_net=format_money_display(b.net_minor, group.currency),
            )
            for b in balances
        ]
        transfer_data = [
            SettlementTransferData(
                from_name=t.from_name,
                to_name=t.to_name,
                amount_minor=t.amount_minor,
                formatted_amount=format_money_display(t.amount_minor, group.currency),
            )
            for t in transfers
        ]

        return (
            SplitBillResponseData(
                action="balances",
                group_name=group.name,
                currency=group.currency,
                balances=balance_data,
                transfers=transfer_data,
                count=len(transfer_data),
            ),
            spoken,
        )

    async def _handle_settle(
        self,
        user_id: uuid.UUID,
        request: SplitBillRequest,
    ) -> tuple[SplitBillResponseData, str]:
        """Record a debt settlement between two group members."""
        if not request.group or not request.group.strip():
            raise InvalidInputError("Please specify the group name for settlement.")

        if not request.settle_from or not request.settle_from.strip():
            raise InvalidInputError("Please specify who is paying the settlement.")

        if not request.settle_to or not request.settle_to.strip():
            raise InvalidInputError("Please specify who is receiving the settlement.")

        if request.amount is None:
            raise InvalidInputError("Please specify the settlement amount.")

        group_name = request.group.strip()
        from_name = request.settle_from.strip()
        to_name = request.settle_to.strip()

        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemySplitBillRepository(uow.session)
            group = await repo.get_group_by_name(user_id, group_name)
            if group is None:
                raise NotFoundError(f"No group found with name '{group_name}'.")

            amount_minor = parse_to_minor_units(request.amount, group.currency)
            await repo.create_settlement(
                group_id=group.id,
                from_name=from_name,
                to_name=to_name,
                amount_minor=amount_minor,
            )

        spoken = format_settlement_spoken(from_name, to_name, amount_minor, group.currency)
        return (
            SplitBillResponseData(
                action="settle",
                group_name=group.name,
                currency=group.currency,
                count=1,
            ),
            spoken,
        )

    async def _handle_create_group(
        self,
        user_id: uuid.UUID,
        request: SplitBillRequest,
    ) -> tuple[SplitBillResponseData, str]:
        """Create a new named group."""
        if not request.group or not request.group.strip():
            raise InvalidInputError("Please specify a group name.")

        group_name = request.group.strip()
        currency = (request.currency or "INR").upper().strip()

        members: list[str] = []
        if isinstance(request.participants, list):
            members = [p.strip() for p in request.participants if p.strip()]
        elif isinstance(request.participants, str):
            members = [p.strip() for p in request.participants.split(",") if p.strip()]

        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemySplitBillRepository(uow.session)
            existing = await repo.get_group_by_name(user_id, group_name)
            if existing is not None:
                raise InvalidInputError(f"Group '{group_name}' already exists.")

            group = await repo.create_group(
                user_id=user_id,
                name=group_name,
                currency=currency,
                members=members,
            )
            created_members = await repo.get_group_members(group.id)
            member_names = [m.name for m in created_members]

        spoken = f"Created group {group.name} with {len(member_names)} members."
        g_data = GroupSummaryData(
            id=str(group.id),
            name=group.name,
            currency=group.currency,
            members=member_names,
        )
        return (
            SplitBillResponseData(
                action="create_group",
                group_name=group.name,
                currency=group.currency,
                groups=[g_data],
                count=1,
            ),
            spoken,
        )

    async def _handle_list_groups(
        self,
        user_id: uuid.UUID,
        _request: SplitBillRequest,
    ) -> tuple[SplitBillResponseData, str]:
        """List all groups owned by a user."""
        async with UnitOfWork(self.session_factory) as uow:
            repo = SQLAlchemySplitBillRepository(uow.session)
            groups = await repo.list_groups(user_id)
            summaries: list[GroupSummaryData] = []
            for g in groups:
                members = await repo.get_group_members(g.id)
                summaries.append(
                    GroupSummaryData(
                        id=str(g.id),
                        name=g.name,
                        currency=g.currency,
                        members=[m.name for m in members],
                    )
                )

        if not summaries:
            spoken = "You have no bill splitting groups yet. Say, create group Goa Trip to start."
            return (
                SplitBillResponseData(
                    action="list_groups",
                    groups=[],
                    count=0,
                ),
                spoken,
            )

        names = [g.name for g in summaries[:4]]
        n = len(summaries)
        count_str = f"{n} group" if n == 1 else f"{n} groups"
        spoken = f"You have {count_str}: {', and '.join(names)}."
        return (
            SplitBillResponseData(
                action="list_groups",
                groups=summaries,
                count=len(summaries),
            ),
            spoken,
        )
