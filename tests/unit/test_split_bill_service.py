"""Unit tests for SplitBillService lifecycle, group calculations, and settlements (T6.3)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sahayak.core.config import get_settings
from sahayak.core.db.session import UnitOfWork
from sahayak.core.errors import InvalidInputError, NotFoundError
from sahayak.modules.finance.schemas import SplitBillAction, SplitBillRequest
from sahayak.modules.finance.service.split_bill import SplitBillService
from sahayak.shared.users.models import User


@pytest.mark.asyncio
async def test_split_bill_service_lifecycle() -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    user_id = uuid.uuid4()
    service = SplitBillService(session_factory=session_factory)

    try:
        async with UnitOfWork(session_factory) as uow:
            uow.session.add(User(id=user_id))
            await uow.session.flush()

        # 1. Standalone split (no group)
        req_standalone = SplitBillRequest(
            action=SplitBillAction.SPLIT,
            amount=1200,
            currency="INR",
            participants=["Alice", "Bob", "Charlie"],
            payer="You",
        )
        res_standalone, spoken_standalone = await service.execute(user_id, req_standalone)
        assert res_standalone.count == 4  # You + Alice + Bob + Charlie
        assert "Split 1200 rupees among 4 people" in spoken_standalone
        assert res_standalone.total_minor == 120000

        # 2. Create group 'Goa Trip'
        req_grp = SplitBillRequest(
            action=SplitBillAction.CREATE_GROUP,
            group="Goa Trip",
            participants=["Alice", "Bob"],
        )
        res_grp, spoken_grp = await service.execute(user_id, req_grp)
        assert "Created group Goa Trip with 3 members" in spoken_grp

        # 3. List groups
        res_list_grp, spoken_list_grp = await service.execute(
            user_id,
            SplitBillRequest(action=SplitBillAction.LIST_GROUPS),
        )
        assert res_list_grp.count == 1
        assert "Goa Trip" in spoken_list_grp

        # 4. Add expense to 'Goa Trip': You paid 1500 for dinner for You, Alice, Bob
        req_split_grp = SplitBillRequest(
            action=SplitBillAction.SPLIT,
            amount=1500,
            currency="INR",
            group="Goa Trip",
            participants=["You", "Alice", "Bob"],
            payer="You",
            description="Dinner at Fisherman's Wharf",
        )
        res_split_grp, spoken_split_grp = await service.execute(user_id, req_split_grp)
        assert "Split 1500 rupees among 3 people" in spoken_split_grp
        # Each owes 500 INR (50,000 minor)

        # 5. Check balances for Goa Trip
        req_bal = SplitBillRequest(
            action=SplitBillAction.BALANCES,
            group="Goa Trip",
        )
        res_bal, spoken_bal = await service.execute(user_id, req_bal)
        assert res_bal.count == 2  # Alice owes You, Bob owes You
        assert "Alice owes You 500 rupees" in spoken_bal or "Bob owes You 500 rupees" in spoken_bal

        # 6. Settle debt from Alice to You: Alice pays 500 INR
        req_settle = SplitBillRequest(
            action=SplitBillAction.SETTLE,
            group="Goa Trip",
            settle_from="Alice",
            settle_to="You",
            amount=500,
        )
        res_settle, spoken_settle = await service.execute(user_id, req_settle)
        assert "Recorded settlement of 500 rupees from Alice to You." in spoken_settle

        # 7. Check balances again: Only Bob owes You 500 INR now
        res_bal2, spoken_bal2 = await service.execute(user_id, req_bal)
        assert res_bal2.count == 1
        assert "Bob owes You 500 rupees" in spoken_bal2

    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_split_bill_service_errors() -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    user_id = uuid.uuid4()
    service = SplitBillService(session_factory=session_factory)

    try:
        # Split with missing amount
        with pytest.raises(InvalidInputError):
            await service.execute(
                user_id,
                SplitBillRequest(
                    action=SplitBillAction.SPLIT, amount=None, participants=["A", "B"]
                ),
            )

        # Split with single participant
        with pytest.raises(InvalidInputError):
            await service.execute(
                user_id,
                SplitBillRequest(action=SplitBillAction.SPLIT, amount=500, participants=[]),
            )

        # Balances with missing group
        with pytest.raises(InvalidInputError):
            await service.execute(
                user_id,
                SplitBillRequest(action=SplitBillAction.BALANCES, group=""),
            )

        # Balances for non-existent group
        with pytest.raises(NotFoundError):
            await service.execute(
                user_id,
                SplitBillRequest(action=SplitBillAction.BALANCES, group="Phantom Group"),
            )

        # Settle with missing details
        with pytest.raises(InvalidInputError):
            await service.execute(
                user_id,
                SplitBillRequest(
                    action=SplitBillAction.SETTLE,
                    group="Goa Trip",
                    settle_from="",
                    settle_to="You",
                    amount=100,
                ),
            )

    finally:
        await engine.dispose()
