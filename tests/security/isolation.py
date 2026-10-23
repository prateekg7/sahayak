"""User isolation testing harness and auto-discovery verification (T1.9)."""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any, cast

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.server.mcpserver import MCPServer


@dataclass(frozen=True)
class ToolIsolationSpec:
    """Security and user isolation specification for an MCP tool."""

    name: str
    allows_anonymous: bool
    required_scopes: list[str] = field(default_factory=list)
    sample_args: dict[str, Any] = field(default_factory=dict)
    custom_isolation_check: (
        Callable[[ClientSession, ClientSession], Coroutine[Any, Any, None]] | None
    ) = None
    setup_sample_args: Callable[[ClientSession], Coroutine[Any, Any, dict[str, Any]]] | None = None


ISOLATION_REGISTRY: dict[str, ToolIsolationSpec] = {}


def register_isolation_spec(spec: ToolIsolationSpec) -> None:
    """Register isolation test coverage for a specific tool."""
    ISOLATION_REGISTRY[spec.name] = spec


def get_untested_tools(server: MCPServer) -> list[str]:
    """Return all tool names registered on the server that lack an isolation spec."""
    tools = server._tool_manager.list_tools()
    registered_names = set(ISOLATION_REGISTRY.keys())
    return [t.name for t in tools if t.name not in registered_names]


def make_test_jwt(
    key: rsa.RSAPrivateKey,
    *,
    sub: str,
    scope: str = "",
    expires_in: int = 3600,
) -> str:
    """Helper to mint a valid test token."""
    now = int(time.time())
    payload = {
        "sub": sub,
        "iss": "https://auth.example.com",
        "aud": "sahayak-api",
        "exp": now + expires_in,
        "iat": now,
        "nbf": now,
        "scope": scope,
    }
    return jwt.encode(payload, key, algorithm="RS256", headers={"kid": "sec-test-key"})


async def assert_user_isolation(
    spec: ToolIsolationSpec,
    app: Any,
    rsa_key: rsa.RSAPrivateKey,
) -> None:
    """Assert that a tool strictly enforces anonymous/authenticated isolation."""
    asgi_transport = httpx.ASGITransport(app=app)

    # 1. Test anonymous access
    async with (
        httpx.AsyncClient(transport=asgi_transport, base_url="http://testserver") as client,
        streamable_http_client("http://testserver/mcp", http_client=cast(Any, client)) as (r, w),
        ClientSession(r, w) as session,
    ):
        await session.initialize()
        args = (
            await spec.setup_sample_args(session)
            if spec.setup_sample_args is not None
            else spec.sample_args
        )
        res = await session.call_tool(spec.name, arguments=args)
        data = json.loads(getattr(res.content[0], "text", "{}"))

        if spec.allows_anonymous:
            assert data.get("ok") is True, f"Anonymous tool {spec.name} failed: {data}"
        else:
            assert data.get("ok") is False, (
                f"Protected tool {spec.name} should fail anonymously: {data}"
            )
            assert data.get("error_code") == "auth_required"

    # 2. If tool requires scopes, test missing scope rejection
    if not spec.allows_anonymous and spec.required_scopes:
        token_wrong_scope = make_test_jwt(rsa_key, sub="user-wrong-scope", scope="unrelated.scope")
        headers = {"Authorization": f"Bearer {token_wrong_scope}"}

        async with (
            httpx.AsyncClient(
                transport=asgi_transport, base_url="http://testserver", headers=headers
            ) as client,
            streamable_http_client("http://testserver/mcp", http_client=cast(Any, client)) as (
                r,
                w,
            ),
            ClientSession(r, w) as session,
        ):
            await session.initialize()
            args = (
                await spec.setup_sample_args(session)
                if spec.setup_sample_args is not None
                else spec.sample_args
            )
            res = await session.call_tool(spec.name, arguments=args)
            data = json.loads(getattr(res.content[0], "text", "{}"))
            assert data.get("ok") is False
            assert data.get("error_code") == "forbidden"

    # 3. Test cross-user isolation when authenticated
    if not spec.allows_anonymous or spec.custom_isolation_check is not None:
        sub_a = f"user-a-{spec.name}-{uuid.uuid4().hex[:8]}"
        sub_b = f"user-b-{spec.name}-{uuid.uuid4().hex[:8]}"
        token_user_a = make_test_jwt(
            rsa_key, sub=sub_a, scope=" ".join(spec.required_scopes or ["academics.read"])
        )
        token_user_b = make_test_jwt(
            rsa_key, sub=sub_b, scope=" ".join(spec.required_scopes or ["academics.read"])
        )

        headers_a = {"Authorization": f"Bearer {token_user_a}"}
        headers_b = {"Authorization": f"Bearer {token_user_b}"}

        async with (
            httpx.AsyncClient(
                transport=asgi_transport, base_url="http://testserver", headers=headers_a
            ) as client_a,
            httpx.AsyncClient(
                transport=asgi_transport, base_url="http://testserver", headers=headers_b
            ) as client_b,
            streamable_http_client("http://testserver/mcp", http_client=cast(Any, client_a)) as (
                ra,
                wa,
            ),
            streamable_http_client("http://testserver/mcp", http_client=cast(Any, client_b)) as (
                rb,
                wb,
            ),
            ClientSession(ra, wa) as session_a,
            ClientSession(rb, wb) as session_b,
        ):
            await session_a.initialize()
            await session_b.initialize()

            # Execute standard call under User A
            args_a = (
                await spec.setup_sample_args(session_a)
                if spec.setup_sample_args is not None
                else spec.sample_args
            )
            res_a = await session_a.call_tool(spec.name, arguments=args_a)
            data_a = json.loads(getattr(res_a.content[0], "text", "{}"))
            assert data_a.get("ok") is True, f"User A failed to call {spec.name}: {data_a}"

            # Execute standard call under User B
            args_b = (
                await spec.setup_sample_args(session_b)
                if spec.setup_sample_args is not None
                else spec.sample_args
            )
            res_b = await session_b.call_tool(spec.name, arguments=args_b)
            data_b = json.loads(getattr(res_b.content[0], "text", "{}"))
            assert data_b.get("ok") is True, f"User B failed to call {spec.name}: {data_b}"

            # If custom isolation check provided, run it
            if spec.custom_isolation_check is not None:
                await spec.custom_isolation_check(session_a, session_b)


# Register initial built-in tool isolation specifications
register_isolation_spec(
    ToolIsolationSpec(
        name="ping_echo",
        allows_anonymous=True,
        sample_args={"message": "hello security"},
    )
)

register_isolation_spec(
    ToolIsolationSpec(
        name="quiz_start",
        allows_anonymous=True,
        sample_args={"topic": "General Science", "num_questions": 3},
    )
)


async def _quiz_answer_setup(session: ClientSession) -> dict[str, Any]:
    res = await session.call_tool("quiz_start", {"topic": "General Science", "num_questions": 3})
    data = json.loads(getattr(res.content[0], "text", "{}"))
    quiz_id = data.get("data", {}).get("quiz_id", "")
    return {"quiz_id": quiz_id, "answer": "A"}


async def _quiz_answer_cross_user_isolation(
    session_a: ClientSession, session_b: ClientSession
) -> None:
    # User A starts a quiz
    res_a = await session_a.call_tool(
        "quiz_start", {"topic": "General Science", "num_questions": 3}
    )
    data_a = json.loads(getattr(res_a.content[0], "text", "{}"))
    quiz_id_a = data_a.get("data", {}).get("quiz_id", "")
    assert quiz_id_a, "Failed to get quiz_id for User A"

    # User B tries to answer User A's quiz
    res_b = await session_b.call_tool("quiz_answer", {"quiz_id": quiz_id_a, "answer": "A"})
    data_b = json.loads(getattr(res_b.content[0], "text", "{}"))
    assert data_b.get("ok") is False, (
        f"User B should be forbidden from answering User A's quiz: {data_b}"
    )
    assert data_b.get("error_code") == "forbidden"


register_isolation_spec(
    ToolIsolationSpec(
        name="quiz_answer",
        allows_anonymous=True,
        setup_sample_args=_quiz_answer_setup,
        custom_isolation_check=_quiz_answer_cross_user_isolation,
    )
)


async def _flashcards_cross_user_isolation(
    session_a: ClientSession, session_b: ClientSession
) -> None:
    # User A creates a flashcard
    res_a = await session_a.call_tool(
        "flashcards",
        {"action": "add", "front": "Mitosis stage 1", "back": "Prophase", "deck": "Biology"},
    )
    data_a = json.loads(getattr(res_a.content[0], "text", "{}"))
    assert data_a.get("ok") is True, f"User A failed to add flashcard: {data_a}"
    card_id = data_a.get("data", {}).get("card", {}).get("card_id", "")
    assert card_id, "Failed to get card_id from User A's response"

    # User B lists due cards - User A's card must not appear
    res_b_list = await session_b.call_tool("flashcards", {"action": "list_due"})
    data_b_list = json.loads(getattr(res_b_list.content[0], "text", "{}"))
    assert data_b_list.get("ok") is True
    b_card_ids = [c.get("card_id") for c in data_b_list.get("data", {}).get("cards", [])]
    assert card_id not in b_card_ids, "User A's card leaked into User B's due list"

    # User B attempts to grade User A's card - must fail with not_found
    res_b_grade = await session_b.call_tool(
        "flashcards",
        {"action": "grade", "card_id": card_id, "rating": "good"},
    )
    data_b_grade = json.loads(getattr(res_b_grade.content[0], "text", "{}"))
    assert data_b_grade.get("ok") is False
    assert data_b_grade.get("error_code") == "not_found"


register_isolation_spec(
    ToolIsolationSpec(
        name="flashcards",
        allows_anonymous=False,
        sample_args={"action": "list_due"},
        custom_isolation_check=_flashcards_cross_user_isolation,
    )
)


async def _study_plan_cross_user_isolation(
    session_a: ClientSession, session_b: ClientSession
) -> None:
    # User A creates a study plan
    res_a = await session_a.call_tool(
        "study_plan",
        {
            "action": "create",
            "goal": "Organic Chemistry",
            "exam_date": "2026-11-20",
            "topics": ["Alkanes", "Alkenes"],
        },
    )
    data_a = json.loads(getattr(res_a.content[0], "text", "{}"))
    assert data_a.get("ok") is True, f"User A failed to create study plan: {data_a}"
    plan_id = data_a.get("data", {}).get("plan_id", "")
    assert plan_id, "Failed to get plan_id from User A's response"

    # User B lists study plans - User A's plan must not appear
    res_b_list = await session_b.call_tool("study_plan", {"action": "list"})
    data_b_list = json.loads(getattr(res_b_list.content[0], "text", "{}"))
    assert data_b_list.get("ok") is True
    b_plan_ids = [p.get("plan_id") for p in data_b_list.get("data", {}).get("plans", [])]
    assert plan_id not in b_plan_ids, "User A's plan leaked into User B's list"

    # User B attempts to access User A's plan today tasks with plan_id - must fail with not_found
    res_b_today = await session_b.call_tool(
        "study_plan",
        {"action": "today", "plan_id": plan_id},
    )
    data_b_today = json.loads(getattr(res_b_today.content[0], "text", "{}"))
    assert data_b_today.get("ok") is False
    assert data_b_today.get("error_code") == "not_found"


register_isolation_spec(
    ToolIsolationSpec(
        name="study_plan",
        allows_anonymous=False,
        sample_args={"action": "list"},
        custom_isolation_check=_study_plan_cross_user_isolation,
    )
)


async def _progress_report_cross_user_isolation(
    session_a: ClientSession, session_b: ClientSession
) -> None:
    # 1. User B reads initial quiz count
    res_b_before = await session_b.call_tool("progress_report", {"scope": "summary"})
    data_b_before = json.loads(getattr(res_b_before.content[0], "text", "{}"))
    assert data_b_before.get("ok") is True, (
        f"User B initial progress_report failed: {data_b_before}"
    )
    quizzes_b_before = data_b_before.get("data", {}).get("total_quizzes", 0)

    # 2. User A starts a quiz on seeded topic General Science
    res_start = await session_a.call_tool(
        "quiz_start",
        {"topic": "General Science", "num_questions": 3},
    )
    data_start = json.loads(getattr(res_start.content[0], "text", "{}"))
    assert data_start.get("ok") is True, f"User A quiz_start failed: {data_start}"

    # 3. User B calls progress_report - User B's total quizzes is unchanged
    res_b_after = await session_b.call_tool("progress_report", {"scope": "summary"})
    data_b_after = json.loads(getattr(res_b_after.content[0], "text", "{}"))
    assert data_b_after.get("ok") is True, f"User B progress_report after failed: {data_b_after}"
    quizzes_b_after = data_b_after.get("data", {}).get("total_quizzes", 0)
    assert quizzes_b_after == quizzes_b_before, (
        "User A's new quiz leaked into User B's total_quizzes count"
    )


register_isolation_spec(
    ToolIsolationSpec(
        name="progress_report",
        allows_anonymous=False,
        sample_args={"scope": "summary"},
        custom_isolation_check=_progress_report_cross_user_isolation,
    )
)

register_isolation_spec(
    ToolIsolationSpec(
        name="topic_brief",
        allows_anonymous=True,
        sample_args={"topic": "General Science", "length": "short"},
    )
)


async def _tasks_cross_user_isolation(session_a: ClientSession, session_b: ClientSession) -> None:
    # User A creates a task
    res_a = await session_a.call_tool(
        "tasks",
        {
            "action": "create",
            "title": "Private task for User A",
            "due_date": "tomorrow",
        },
    )
    data_a = json.loads(getattr(res_a.content[0], "text", "{}"))
    assert data_a.get("ok") is True
    task_id = data_a.get("data", {}).get("task", {}).get("id")
    assert task_id

    # User B lists tasks - User A's task must not appear
    res_b_list = await session_b.call_tool("tasks", {"action": "list"})
    data_b_list = json.loads(getattr(res_b_list.content[0], "text", "{}"))
    assert data_b_list.get("ok") is True
    b_task_ids = [t.get("id") for t in data_b_list.get("data", {}).get("tasks", [])]
    assert task_id not in b_task_ids

    # User B attempts to complete User A's task - must fail with not_found
    res_b_comp = await session_b.call_tool(
        "tasks",
        {"action": "complete", "task_id": task_id},
    )
    data_b_comp = json.loads(getattr(res_b_comp.content[0], "text", "{}"))
    assert data_b_comp.get("ok") is False
    assert data_b_comp.get("error_code") == "not_found"


register_isolation_spec(
    ToolIsolationSpec(
        name="tasks",
        allows_anonymous=False,
        sample_args={"action": "list"},
        custom_isolation_check=_tasks_cross_user_isolation,
    )
)


async def _habits_cross_user_isolation(session_a: ClientSession, session_b: ClientSession) -> None:
    # User A creates a habit
    res_a = await session_a.call_tool(
        "habits",
        {
            "action": "create",
            "name": "User A Private Meditation",
        },
    )
    data_a = json.loads(getattr(res_a.content[0], "text", "{}"))
    assert data_a.get("ok") is True
    habit_id = data_a.get("data", {}).get("habit", {}).get("id")
    assert habit_id

    # User B lists habits - User A's habit must not appear
    res_b_list = await session_b.call_tool("habits", {"action": "list"})
    data_b_list = json.loads(getattr(res_b_list.content[0], "text", "{}"))
    assert data_b_list.get("ok") is True
    b_habit_ids = [h.get("id") for h in data_b_list.get("data", {}).get("habits", [])]
    assert habit_id not in b_habit_ids

    # User B attempts to log User A's habit - must fail with not_found
    res_b_log = await session_b.call_tool(
        "habits",
        {"action": "log", "habit_id": habit_id},
    )
    data_b_log = json.loads(getattr(res_b_log.content[0], "text", "{}"))
    assert data_b_log.get("ok") is False
    assert data_b_log.get("error_code") == "not_found"


register_isolation_spec(
    ToolIsolationSpec(
        name="habits",
        allows_anonymous=False,
        sample_args={"action": "list"},
        custom_isolation_check=_habits_cross_user_isolation,
    )
)


async def _notes_cross_user_isolation(session_a: ClientSession, session_b: ClientSession) -> None:
    # User A creates a note
    res_a = await session_a.call_tool(
        "notes",
        {
            "action": "add",
            "content": "Secret password phrase 12345",
        },
    )
    data_a = json.loads(getattr(res_a.content[0], "text", "{}"))
    assert data_a.get("ok") is True
    note_id = data_a.get("data", {}).get("note", {}).get("id")
    assert note_id

    # User B searches notes for phrase - User A's note must not appear
    res_b_search = await session_b.call_tool(
        "notes",
        {"action": "search", "query": "Secret"},
    )
    data_b_search = json.loads(getattr(res_b_search.content[0], "text", "{}"))
    assert data_b_search.get("ok") is True
    b_notes = data_b_search.get("data", {}).get("notes", [])
    b_note_ids = [n.get("id") for n in b_notes]
    assert note_id not in b_note_ids

    # User B attempts to delete User A's note - must fail with not_found
    res_b_del = await session_b.call_tool(
        "notes",
        {"action": "delete", "note_id": note_id},
    )
    data_b_del = json.loads(getattr(res_b_del.content[0], "text", "{}"))
    assert data_b_del.get("ok") is False
    assert data_b_del.get("error_code") == "not_found"


register_isolation_spec(
    ToolIsolationSpec(
        name="notes",
        allows_anonymous=False,
        sample_args={"action": "add", "content": "Sample note content"},
        custom_isolation_check=_notes_cross_user_isolation,
    )
)


async def _focus_timer_cross_user_isolation(
    session_a: ClientSession, session_b: ClientSession
) -> None:
    # User A starts a 25 minute focus session
    res_a = await session_a.call_tool(
        "focus_timer",
        {
            "action": "start",
            "duration_minutes": 25,
            "task_label": "User A Private Study",
        },
    )
    data_a = json.loads(getattr(res_a.content[0], "text", "{}"))
    assert data_a.get("ok") is True
    session_id = data_a.get("data", {}).get("session", {}).get("id")
    assert session_id

    # User B checks status - User B must have no active session
    res_b_stat = await session_b.call_tool(
        "focus_timer",
        {"action": "status"},
    )
    data_b_stat = json.loads(getattr(res_b_stat.content[0], "text", "{}"))
    assert data_b_stat.get("ok") is True
    assert "not have an active focus session" in data_b_stat.get("spoken_summary", "")

    # User B attempts to stop session - must fail with not_found
    res_b_stop = await session_b.call_tool(
        "focus_timer",
        {"action": "stop"},
    )
    data_b_stop = json.loads(getattr(res_b_stop.content[0], "text", "{}"))
    assert data_b_stop.get("ok") is False
    assert data_b_stop.get("error_code") == "not_found"

    # User A stops their own session
    res_a_stop = await session_a.call_tool(
        "focus_timer",
        {"action": "stop"},
    )
    data_a_stop = json.loads(getattr(res_a_stop.content[0], "text", "{}"))
    assert data_a_stop.get("ok") is True


register_isolation_spec(
    ToolIsolationSpec(
        name="focus_timer",
        allows_anonymous=False,
        sample_args={"action": "status"},
        custom_isolation_check=_focus_timer_cross_user_isolation,
    )
)


async def _daily_briefing_cross_user_isolation(
    session_a: ClientSession, session_b: ClientSession
) -> None:
    # User A creates a task due today
    res_a_task = await session_a.call_tool(
        "tasks",
        {
            "action": "create",
            "title": "Private briefing task for User A",
            "due_date": "today",
        },
    )
    data_a_task = json.loads(getattr(res_a_task.content[0], "text", "{}"))
    assert data_a_task.get("ok") is True

    # User A daily briefing includes the task
    res_a_brief = await session_a.call_tool("daily_briefing", {})
    data_a_brief = json.loads(getattr(res_a_brief.content[0], "text", "{}"))
    assert data_a_brief.get("ok") is True
    assert data_a_brief.get("data", {}).get("tasks_due_count", 0) >= 1

    # User B daily briefing does NOT include User A's task
    res_b_brief = await session_b.call_tool("daily_briefing", {})
    data_b_brief = json.loads(getattr(res_b_brief.content[0], "text", "{}"))
    assert data_b_brief.get("ok") is True
    b_tasks = data_b_brief.get("data", {}).get("tasks_due", [])
    assert "Private briefing task for User A" not in b_tasks


register_isolation_spec(
    ToolIsolationSpec(
        name="daily_briefing",
        allows_anonymous=False,
        sample_args={},
        custom_isolation_check=_daily_briefing_cross_user_isolation,
    )
)


async def _expense_log_cross_user_isolation(
    session_a: ClientSession, session_b: ClientSession
) -> None:
    # User A logs an expense
    res_a = await session_a.call_tool(
        "expense_log",
        {
            "action": "add",
            "amount": 250,
            "currency": "INR",
            "category": "groceries",
            "note": "Private Organic Groceries",
        },
    )
    data_a = json.loads(getattr(res_a.content[0], "text", "{}"))
    assert data_a.get("ok") is True
    exp_id = data_a.get("data", {}).get("expense", {}).get("id")
    assert exp_id

    # User B lists expenses - User A's expense must not appear
    res_b_list = await session_b.call_tool("expense_log", {"action": "list"})
    data_b_list = json.loads(getattr(res_b_list.content[0], "text", "{}"))
    assert data_b_list.get("ok") is True
    b_ids = [e.get("id") for e in data_b_list.get("data", {}).get("expenses", [])]
    assert exp_id not in b_ids

    # User B attempts to delete User A's expense - must fail with not_found
    res_b_del = await session_b.call_tool(
        "expense_log",
        {"action": "delete", "expense_id": exp_id},
    )
    data_b_del = json.loads(getattr(res_b_del.content[0], "text", "{}"))
    assert data_b_del.get("ok") is False
    assert data_b_del.get("error_code") == "not_found"


register_isolation_spec(
    ToolIsolationSpec(
        name="expense_log",
        allows_anonymous=False,
        sample_args={"action": "list"},
        custom_isolation_check=_expense_log_cross_user_isolation,
    )
)


async def _budget_cross_user_isolation(session_a: ClientSession, session_b: ClientSession) -> None:
    # User A sets a budget
    res_a = await session_a.call_tool(
        "budget",
        {"action": "set", "category": "groceries", "amount": 5000, "currency": "INR"},
    )
    data_a = json.loads(getattr(res_a.content[0], "text", "{}"))
    assert data_a.get("ok") is True

    # User B lists budgets - User A's budget must not appear
    res_b_list = await session_b.call_tool("budget", {"action": "list"})
    data_b_list = json.loads(getattr(res_b_list.content[0], "text", "{}"))
    assert data_b_list.get("ok") is True
    assert data_b_list.get("data", {}).get("count") == 0

    # User B attempts to remove User A's budget - must fail with not_found
    res_b_rem = await session_b.call_tool("budget", {"action": "remove", "category": "groceries"})
    data_b_rem = json.loads(getattr(res_b_rem.content[0], "text", "{}"))
    assert data_b_rem.get("ok") is False
    assert data_b_rem.get("error_code") == "not_found"


register_isolation_spec(
    ToolIsolationSpec(
        name="budget",
        allows_anonymous=False,
        sample_args={"action": "list"},
        custom_isolation_check=_budget_cross_user_isolation,
    )
)


async def _split_bill_cross_user_isolation(
    session_a: ClientSession, session_b: ClientSession
) -> None:
    group_name = f"Private Trip {uuid.uuid4().hex[:6]}"
    # User A creates a group
    res_a = await session_a.call_tool(
        "split_bill",
        {"action": "create_group", "group": group_name, "participants": ["Bob"]},
    )
    data_a = json.loads(getattr(res_a.content[0], "text", "{}"))
    assert data_a.get("ok") is True

    # User B lists groups - User A's group must not appear
    res_b_list = await session_b.call_tool("split_bill", {"action": "list_groups"})
    data_b_list = json.loads(getattr(res_b_list.content[0], "text", "{}"))
    assert data_b_list.get("ok") is True
    b_names = [g.get("name") for g in data_b_list.get("data", {}).get("groups", [])]
    assert group_name not in b_names

    # User B attempts to view balances of User A's group - must fail with not_found
    res_b_bal = await session_b.call_tool("split_bill", {"action": "balances", "group": group_name})
    data_b_bal = json.loads(getattr(res_b_bal.content[0], "text", "{}"))
    assert data_b_bal.get("ok") is False
    assert data_b_bal.get("error_code") == "not_found"


register_isolation_spec(
    ToolIsolationSpec(
        name="split_bill",
        allows_anonymous=False,
        sample_args={"action": "list_groups"},
        custom_isolation_check=_split_bill_cross_user_isolation,
    )
)


async def _finance_report_cross_user_isolation(
    session_a: ClientSession, session_b: ClientSession
) -> None:
    bill_name = f"Private Rent {uuid.uuid4().hex[:6]}"
    # User A adds a bill
    res_a = await session_a.call_tool(
        "finance_report",
        {"action": "add_bill", "bill_name": bill_name, "amount": 25000, "due_day": 5},
    )
    data_a = json.loads(getattr(res_a.content[0], "text", "{}"))
    assert data_a.get("ok") is True
    bill_id = data_a.get("data", {}).get("bill", {}).get("id")
    assert bill_id is not None

    # User B queries bills_due - User A's bill must not appear
    res_b_list = await session_b.call_tool(
        "finance_report", {"action": "bills_due", "due_days_ahead": 35}
    )
    data_b_list = json.loads(getattr(res_b_list.content[0], "text", "{}"))
    assert data_b_list.get("ok") is True
    b_bills = data_b_list.get("data", {}).get("bills", [])
    b_names = [b.get("name") for b in b_bills]
    assert bill_name not in b_names

    # User B attempts to mark User A's bill paid - must fail with not_found
    res_b_pay = await session_b.call_tool(
        "finance_report", {"action": "mark_bill_paid", "bill_id": bill_id}
    )
    data_b_pay = json.loads(getattr(res_b_pay.content[0], "text", "{}"))
    assert data_b_pay.get("ok") is False
    assert data_b_pay.get("error_code") == "not_found"


register_isolation_spec(
    ToolIsolationSpec(
        name="finance_report",
        allows_anonymous=False,
        sample_args={"action": "summary"},
        custom_isolation_check=_finance_report_cross_user_isolation,
    )
)


async def _health_log_cross_user_isolation(
    session_a: ClientSession, session_b: ClientSession
) -> None:
    # User A logs water
    res_a = await session_a.call_tool(
        "health_log",
        {"action": "log", "kind": "water", "value": 500, "unit": "ml"},
    )
    data_a = json.loads(getattr(res_a.content[0], "text", "{}"))
    assert data_a.get("ok") is True
    entry_id = data_a.get("data", {}).get("entry", {}).get("id")
    assert entry_id is not None

    # User B queries list - User A's entry must not appear
    res_b_list = await session_b.call_tool("health_log", {"action": "list", "kind": "water"})
    data_b_list = json.loads(getattr(res_b_list.content[0], "text", "{}"))
    assert data_b_list.get("ok") is True
    b_entries = data_b_list.get("data", {}).get("entries", [])
    b_entry_ids = [e.get("id") for e in b_entries]
    assert entry_id not in b_entry_ids

    # User B attempts to delete User A's entry - must fail with not_found
    res_b_del = await session_b.call_tool("health_log", {"action": "delete", "entry_id": entry_id})
    data_b_del = json.loads(getattr(res_b_del.content[0], "text", "{}"))
    assert data_b_del.get("ok") is False
    assert data_b_del.get("error_code") == "not_found"


register_isolation_spec(
    ToolIsolationSpec(
        name="health_log",
        allows_anonymous=False,
        sample_args={"action": "list", "kind": "water"},
        custom_isolation_check=_health_log_cross_user_isolation,
    )
)


async def _health_summary_cross_user_isolation(
    session_a: ClientSession, session_b: ClientSession
) -> None:
    med_name = f"Private Med {uuid.uuid4().hex[:6]}"
    # User A adds medicine
    res_a = await session_a.call_tool(
        "health_summary",
        {"action": "add_medicine", "medicine_name": med_name, "times": ["08:00"]},
    )
    data_a = json.loads(getattr(res_a.content[0], "text", "{}"))
    assert data_a.get("ok") is True

    # User B lists medicines - User A's medicine must not appear
    res_b_list = await session_b.call_tool("health_summary", {"action": "list_medicines"})
    data_b_list = json.loads(getattr(res_b_list.content[0], "text", "{}"))
    assert data_b_list.get("ok") is True
    b_meds = data_b_list.get("data", {}).get("medicines", [])
    b_names = [m.get("name") for m in b_meds]
    assert med_name not in b_names

    # User B attempts to mark User A's medicine taken - must fail with not_found
    res_b_mark = await session_b.call_tool(
        "health_summary", {"action": "mark_taken", "medicine_name": med_name}
    )
    data_b_mark = json.loads(getattr(res_b_mark.content[0], "text", "{}"))
    assert data_b_mark.get("ok") is False
    assert data_b_mark.get("error_code") == "not_found"


register_isolation_spec(
    ToolIsolationSpec(
        name="health_summary",
        allows_anonymous=False,
        sample_args={"action": "today"},
        custom_isolation_check=_health_summary_cross_user_isolation,
    )
)


async def _interview_practice_cross_user_isolation(
    session_a: ClientSession, session_b: ClientSession
) -> None:
    # User A starts an interview
    res_a = await session_a.call_tool(
        "interview_practice",
        {"action": "start", "role": "Software Engineer", "total_questions": 3},
    )
    data_a = json.loads(getattr(res_a.content[0], "text", "{}"))
    assert data_a.get("ok") is True
    session_id = data_a.get("data", {}).get("session_id")
    assert session_id is not None

    # User B attempts to answer User A's session - must fail with not_found
    res_b_ans = await session_b.call_tool(
        "interview_practice",
        {"action": "answer", "session_id": session_id, "answer": "I write comprehensive tests."},
    )
    data_b_ans = json.loads(getattr(res_b_ans.content[0], "text", "{}"))
    assert data_b_ans.get("ok") is False
    assert data_b_ans.get("error_code") == "not_found"

    # User B attempts to finish User A's session - must fail with not_found
    res_b_fin = await session_b.call_tool(
        "interview_practice",
        {"action": "finish", "session_id": session_id},
    )
    data_b_fin = json.loads(getattr(res_b_fin.content[0], "text", "{}"))
    assert data_b_fin.get("ok") is False
    assert data_b_fin.get("error_code") == "not_found"

    # User B requests history - User A's session must not be present
    res_b_hist = await session_b.call_tool("interview_practice", {"action": "history"})
    data_b_hist = json.loads(getattr(res_b_hist.content[0], "text", "{}"))
    assert data_b_hist.get("ok") is True
    b_sessions = data_b_hist.get("data", {}).get("sessions", [])
    b_sids = [s.get("session_id") for s in b_sessions]
    assert session_id not in b_sids


register_isolation_spec(
    ToolIsolationSpec(
        name="interview_practice",
        allows_anonymous=False,
        sample_args={"action": "history"},
        custom_isolation_check=_interview_practice_cross_user_isolation,
    )
)


async def _application_tracker_cross_user_isolation(
    session_a: ClientSession, session_b: ClientSession
) -> None:
    # User A adds an application
    res_a = await session_a.call_tool(
        "application_tracker",
        {"action": "add", "company": "Acme Corp", "role": "Lead Architect"},
    )
    data_a = json.loads(getattr(res_a.content[0], "text", "{}"))
    assert data_a.get("ok") is True
    app_id = data_a.get("data", {}).get("application_id")
    assert app_id is not None

    # User B lists applications - User A's application must not appear
    res_b_list = await session_b.call_tool("application_tracker", {"action": "list"})
    data_b_list = json.loads(getattr(res_b_list.content[0], "text", "{}"))
    assert data_b_list.get("ok") is True
    b_apps = data_b_list.get("data", {}).get("applications", [])
    b_app_ids = [a.get("id") for a in b_apps]
    assert app_id not in b_app_ids

    # User B attempts to update User A's application - must fail with not_found
    res_b_upd = await session_b.call_tool(
        "application_tracker",
        {"action": "update_status", "application_id": app_id, "status": "interviewing"},
    )
    data_b_upd = json.loads(getattr(res_b_upd.content[0], "text", "{}"))
    assert data_b_upd.get("ok") is False
    assert data_b_upd.get("error_code") == "not_found"

    # User B attempts to delete User A's application - must fail with not_found
    res_b_del = await session_b.call_tool(
        "application_tracker",
        {"action": "delete", "application_id": app_id},
    )
    data_b_del = json.loads(getattr(res_b_del.content[0], "text", "{}"))
    assert data_b_del.get("ok") is False
    assert data_b_del.get("error_code") == "not_found"


register_isolation_spec(
    ToolIsolationSpec(
        name="application_tracker",
        allows_anonymous=False,
        sample_args={"action": "list"},
        custom_isolation_check=_application_tracker_cross_user_isolation,
    )
)


async def _career_practice_cross_user_isolation(
    session_a: ClientSession, session_b: ClientSession
) -> None:
    # User A answers daily question
    res_a = await session_a.call_tool(
        "career_practice",
        {
            "action": "check_answer",
            "question_key": "star_method_intro",
            "answer": "STAR stands for situation, task, action, and result.",
        },
    )
    data_a = json.loads(getattr(res_a.content[0], "text", "{}"))
    assert data_a.get("ok") is True, f"User A failed to answer daily question: {data_a}"
    stats_a = data_a.get("data", {}).get("stats", {})
    assert stats_a.get("total_attempts", 0) >= 1

    # User B answers daily question - User B's attempts must be recorded independently
    res_b = await session_b.call_tool(
        "career_practice",
        {
            "action": "check_answer",
            "question_key": "star_method_intro",
            "answer": "Situation task action result to structure interview answers.",
        },
    )
    data_b = json.loads(getattr(res_b.content[0], "text", "{}"))
    assert data_b.get("ok") is True, f"User B failed to answer daily question: {data_b}"
    stats_b = data_b.get("data", {}).get("stats", {})
    assert stats_b.get("total_attempts", 0) >= 1


register_isolation_spec(
    ToolIsolationSpec(
        name="career_practice",
        allows_anonymous=False,
        sample_args={"action": "daily_question"},
        custom_isolation_check=_career_practice_cross_user_isolation,
    )
)


async def _shared_list_cross_user_isolation(
    session_a: ClientSession, session_b: ClientSession
) -> None:
    # User A adds an item to groceries list
    res_a = await session_a.call_tool(
        "shared_list",
        {"action": "add", "item": "Organic Almond Milk", "list_name": "groceries"},
    )
    data_a = json.loads(getattr(res_a.content[0], "text", "{}"))
    assert data_a.get("ok") is True, f"User A failed to add item: {data_a}"
    h_id_a = data_a.get("data", {}).get("household_id")
    assert h_id_a is not None

    # User B adds an item to groceries list
    res_b = await session_b.call_tool(
        "shared_list",
        {"action": "add", "item": "Earl Grey Tea", "list_name": "groceries"},
    )
    data_b = json.loads(getattr(res_b.content[0], "text", "{}"))
    assert data_b.get("ok") is True, f"User B failed to add item: {data_b}"
    h_id_b = data_b.get("data", {}).get("household_id")
    assert h_id_b is not None
    assert h_id_a != h_id_b

    # User A reads list: sees Organic Almond Milk, not Earl Grey Tea
    res_a_read = await session_a.call_tool(
        "shared_list",
        {"action": "read", "list_name": "groceries"},
    )
    data_a_read = json.loads(getattr(res_a_read.content[0], "text", "{}"))
    assert data_a_read.get("ok") is True
    raw_items_a = data_a_read.get("data", {}).get("items", [])
    items_a = [it.get("item_name", "").lower() for it in raw_items_a]
    assert "organic almond milk" in items_a
    assert "earl grey tea" not in items_a

    # User B reads list: sees Earl Grey Tea, not Organic Almond Milk
    res_b_read = await session_b.call_tool(
        "shared_list",
        {"action": "read", "list_name": "groceries"},
    )
    data_b_read = json.loads(getattr(res_b_read.content[0], "text", "{}"))
    assert data_b_read.get("ok") is True
    raw_items_b = data_b_read.get("data", {}).get("items", [])
    items_b = [it.get("item_name", "").lower() for it in raw_items_b]
    assert "earl grey tea" in items_b
    assert "organic almond milk" not in items_b

    # User B attempts to access User A's household list directly
    res_b_breach = await session_b.call_tool(
        "shared_list",
        {"action": "read", "household_id": h_id_a, "list_name": "groceries"},
    )
    data_b_breach = json.loads(getattr(res_b_breach.content[0], "text", "{}"))
    assert data_b_breach.get("ok") is False
    assert data_b_breach.get("error_code") == "not_found"


register_isolation_spec(
    ToolIsolationSpec(
        name="shared_list",
        allows_anonymous=False,
        sample_args={"action": "read"},
        custom_isolation_check=_shared_list_cross_user_isolation,
    )
)


async def _chores_cross_user_isolation(session_a: ClientSession, session_b: ClientSession) -> None:
    # User A creates a chore
    res_a = await session_a.call_tool(
        "chores",
        {"action": "add", "title": "Mow the lawn", "frequency": "weekly"},
    )
    data_a = json.loads(getattr(res_a.content[0], "text", "{}"))
    assert data_a.get("ok") is True, f"User A failed to add chore: {data_a}"
    h_id_a = data_a.get("data", {}).get("household_id")
    assert h_id_a is not None

    # User B creates a chore
    res_b = await session_b.call_tool(
        "chores",
        {"action": "add", "title": "Clean the garage", "frequency": "monthly"},
    )
    data_b = json.loads(getattr(res_b.content[0], "text", "{}"))
    assert data_b.get("ok") is True, f"User B failed to add chore: {data_b}"
    h_id_b = data_b.get("data", {}).get("household_id")
    assert h_id_b is not None
    assert h_id_a != h_id_b

    # User A lists chores: sees Mow the lawn, not Clean the garage
    res_a_list = await session_a.call_tool("chores", {"action": "list"})
    data_a_list = json.loads(getattr(res_a_list.content[0], "text", "{}"))
    assert data_a_list.get("ok") is True
    titles_a = [c.get("title", "").lower() for c in data_a_list.get("data", {}).get("chores", [])]
    assert "mow the lawn" in titles_a
    assert "clean the garage" not in titles_a

    # User B lists chores: sees Clean the garage, not Mow the lawn
    res_b_list = await session_b.call_tool("chores", {"action": "list"})
    data_b_list = json.loads(getattr(res_b_list.content[0], "text", "{}"))
    assert data_b_list.get("ok") is True
    titles_b = [c.get("title", "").lower() for c in data_b_list.get("data", {}).get("chores", [])]
    assert "clean the garage" in titles_b
    assert "mow the lawn" not in titles_b

    # User B attempts to access User A's chores by household_id
    res_b_breach = await session_b.call_tool(
        "chores",
        {"action": "list", "household_id": h_id_a},
    )
    data_b_breach = json.loads(getattr(res_b_breach.content[0], "text", "{}"))
    assert data_b_breach.get("ok") is False
    assert data_b_breach.get("error_code") == "not_found"


register_isolation_spec(
    ToolIsolationSpec(
        name="chores",
        allows_anonymous=False,
        sample_args={"action": "list"},
        custom_isolation_check=_chores_cross_user_isolation,
    )
)


async def _pantry_recipes_cross_user_isolation(
    session_a: ClientSession, session_b: ClientSession
) -> None:
    # User A adds pantry item
    res_a = await session_a.call_tool(
        "pantry_recipes",
        {"action": "pantry_add", "item": "Basmati rice", "quantity": "1 kg"},
    )
    data_a = json.loads(getattr(res_a.content[0], "text", "{}"))
    assert data_a.get("ok") is True, f"User A failed to add pantry item: {data_a}"
    h_id_a = data_a.get("data", {}).get("household_id")
    assert h_id_a is not None

    # User B adds pantry item
    res_b = await session_b.call_tool(
        "pantry_recipes",
        {"action": "pantry_add", "item": "Extra Virgin Olive Oil", "quantity": "500 ml"},
    )
    data_b = json.loads(getattr(res_b.content[0], "text", "{}"))
    assert data_b.get("ok") is True, f"User B failed to add pantry item: {data_b}"
    h_id_b = data_b.get("data", {}).get("household_id")
    assert h_id_b is not None
    assert h_id_a != h_id_b

    # User A lists pantry: sees Basmati rice, not Olive Oil
    res_a_list = await session_a.call_tool("pantry_recipes", {"action": "pantry_list"})
    data_a_list = json.loads(getattr(res_a_list.content[0], "text", "{}"))
    assert data_a_list.get("ok") is True
    items_a = [i.get("item_name", "").lower() for i in data_a_list.get("data", {}).get("items", [])]
    assert "basmati rice" in items_a
    assert "extra virgin olive oil" not in items_a

    # User B lists pantry: sees Olive Oil, not Basmati rice
    res_b_list = await session_b.call_tool("pantry_recipes", {"action": "pantry_list"})
    data_b_list = json.loads(getattr(res_b_list.content[0], "text", "{}"))
    assert data_b_list.get("ok") is True
    items_b = [i.get("item_name", "").lower() for i in data_b_list.get("data", {}).get("items", [])]
    assert "extra virgin olive oil" in items_b
    assert "basmati rice" not in items_b

    # User B attempts to access User A's pantry by household_id
    res_b_breach = await session_b.call_tool(
        "pantry_recipes",
        {"action": "pantry_list", "household_id": h_id_a},
    )
    data_b_breach = json.loads(getattr(res_b_breach.content[0], "text", "{}"))
    assert data_b_breach.get("ok") is False
    assert data_b_breach.get("error_code") == "not_found"


register_isolation_spec(
    ToolIsolationSpec(
        name="pantry_recipes",
        allows_anonymous=False,
        sample_args={"action": "pantry_list"},
        custom_isolation_check=_pantry_recipes_cross_user_isolation,
    )
)


async def _orders_cross_user_isolation(session_a: ClientSession, session_b: ClientSession) -> None:
    # User A creates an order
    res_a = await session_a.call_tool(
        "orders",
        {
            "action": "create",
            "customer_name": "Ramesh",
            "items": [{"item_name": "Notebook", "quantity": 2, "unit_price": 50.0}],
        },
    )
    data_a = json.loads(getattr(res_a.content[0], "text", "{}"))
    assert data_a.get("ok") is True, f"User A failed to create order: {data_a}"
    b_id_a = data_a.get("data", {}).get("business_id")
    order_num_a = data_a.get("data", {}).get("order", {}).get("order_number")
    assert b_id_a is not None and order_num_a is not None

    # User B creates an order
    res_b = await session_b.call_tool(
        "orders",
        {
            "action": "create",
            "customer_name": "Suresh",
            "items": [{"item_name": "Ballpoint Pen", "quantity": 5, "unit_price": 10.0}],
        },
    )
    data_b = json.loads(getattr(res_b.content[0], "text", "{}"))
    assert data_b.get("ok") is True, f"User B failed to create order: {data_b}"
    b_id_b = data_b.get("data", {}).get("business_id")
    assert b_id_a != b_id_b

    # User A lists pending orders: sees Ramesh's order, not Suresh's
    res_a_list = await session_a.call_tool("orders", {"action": "list_pending"})
    data_a_list = json.loads(getattr(res_a_list.content[0], "text", "{}"))
    assert data_a_list.get("ok") is True
    customers_a = [o.get("customer_name") for o in data_a_list.get("data", {}).get("orders", [])]
    assert "Ramesh" in customers_a
    assert "Suresh" not in customers_a

    # User B lists pending orders: sees Suresh's order, not Ramesh's
    res_b_list = await session_b.call_tool("orders", {"action": "list_pending"})
    data_b_list = json.loads(getattr(res_b_list.content[0], "text", "{}"))
    assert data_b_list.get("ok") is True
    customers_b = [o.get("customer_name") for o in data_b_list.get("data", {}).get("orders", [])]
    assert "Suresh" in customers_b
    assert "Ramesh" not in customers_b

    # User B attempts to access User A's order by business_id
    res_b_breach = await session_b.call_tool(
        "orders",
        {"action": "get", "business_id": b_id_a, "order_number": order_num_a},
    )
    data_b_breach = json.loads(getattr(res_b_breach.content[0], "text", "{}"))
    assert data_b_breach.get("ok") is False
    assert data_b_breach.get("error_code") == "not_found"


register_isolation_spec(
    ToolIsolationSpec(
        name="orders",
        allows_anonymous=False,
        sample_args={"action": "list_pending"},
        custom_isolation_check=_orders_cross_user_isolation,
    )
)


async def _ledger_cross_user_isolation(session_a: ClientSession, session_b: ClientSession) -> None:
    # User A records a due for customer Priya
    res_a = await session_a.call_tool(
        "ledger",
        {
            "action": "add_due",
            "customer_name": "Priya",
            "amount": 500.0,
        },
    )
    data_a = json.loads(getattr(res_a.content[0], "text", "{}"))
    assert data_a.get("ok") is True, f"User A failed to add due: {data_a}"
    b_id_a = data_a.get("data", {}).get("business_id")
    assert b_id_a is not None

    # User B records a due for customer Rahul
    res_b = await session_b.call_tool(
        "ledger",
        {
            "action": "add_due",
            "customer_name": "Rahul",
            "amount": 300.0,
        },
    )
    data_b = json.loads(getattr(res_b.content[0], "text", "{}"))
    assert data_b.get("ok") is True, f"User B failed to add due: {data_b}"
    b_id_b = data_b.get("data", {}).get("business_id")
    assert b_id_a != b_id_b

    # User A checks top dues: sees Priya, not Rahul
    res_a_top = await session_a.call_tool("ledger", {"action": "top_dues"})
    data_a_top = json.loads(getattr(res_a_top.content[0], "text", "{}"))
    assert data_a_top.get("ok") is True
    top_names_a = [
        td.get("customer", {}).get("name") for td in data_a_top.get("data", {}).get("top_dues", [])
    ]
    assert "Priya" in top_names_a
    assert "Rahul" not in top_names_a

    # User B checks top dues: sees Rahul, not Priya
    res_b_top = await session_b.call_tool("ledger", {"action": "top_dues"})
    data_b_top = json.loads(getattr(res_b_top.content[0], "text", "{}"))
    assert data_b_top.get("ok") is True
    top_names_b = [
        td.get("customer", {}).get("name") for td in data_b_top.get("data", {}).get("top_dues", [])
    ]
    assert "Rahul" in top_names_b
    assert "Priya" not in top_names_b

    # User B attempts to access User A's customer balance with User A's business_id
    res_b_breach = await session_b.call_tool(
        "ledger",
        {"action": "balance", "business_id": b_id_a, "customer_name": "Priya"},
    )
    data_b_breach = json.loads(getattr(res_b_breach.content[0], "text", "{}"))
    assert data_b_breach.get("ok") is False
    assert data_b_breach.get("error_code") == "not_found"


register_isolation_spec(
    ToolIsolationSpec(
        name="ledger",
        allows_anonymous=False,
        sample_args={"action": "top_dues"},
        custom_isolation_check=_ledger_cross_user_isolation,
    )
)


async def _sales_summary_cross_user_isolation(
    session_a: ClientSession, session_b: ClientSession
) -> None:
    # User A adds a product
    res_a = await session_a.call_tool(
        "sales_summary",
        {
            "action": "add_product",
            "name": "Notebook",
            "stock_level": 25,
            "low_stock_threshold": 5,
        },
    )
    data_a = json.loads(getattr(res_a.content[0], "text", "{}"))
    assert data_a.get("ok") is True, f"User A failed to add product: {data_a}"
    b_id_a = data_a.get("data", {}).get("business_id")
    assert b_id_a is not None

    # User B adds a product
    res_b = await session_b.call_tool(
        "sales_summary",
        {
            "action": "add_product",
            "name": "Gel Pen",
            "stock_level": 100,
            "low_stock_threshold": 10,
        },
    )
    data_b = json.loads(getattr(res_b.content[0], "text", "{}"))
    assert data_b.get("ok") is True, f"User B failed to add product: {data_b}"
    b_id_b = data_b.get("data", {}).get("business_id")
    assert b_id_a != b_id_b

    # User A lists products: sees Notebook, not Gel Pen
    res_a_list = await session_a.call_tool("sales_summary", {"action": "list_products"})
    data_a_list = json.loads(getattr(res_a_list.content[0], "text", "{}"))
    assert data_a_list.get("ok") is True
    prods_a = [p.get("name") for p in data_a_list.get("data", {}).get("products", [])]
    assert "Notebook" in prods_a
    assert "Gel Pen" not in prods_a

    # User B lists products: sees Gel Pen, not Notebook
    res_b_list = await session_b.call_tool("sales_summary", {"action": "list_products"})
    data_b_list = json.loads(getattr(res_b_list.content[0], "text", "{}"))
    assert data_b_list.get("ok") is True
    prods_b = [p.get("name") for p in data_b_list.get("data", {}).get("products", [])]
    assert "Gel Pen" in prods_b
    assert "Notebook" not in prods_b

    # User B attempts to access User A's sales summary using User A's business_id
    res_b_breach = await session_b.call_tool(
        "sales_summary",
        {"action": "today", "business_id": b_id_a},
    )
    data_b_breach = json.loads(getattr(res_b_breach.content[0], "text", "{}"))
    assert data_b_breach.get("ok") is False
    assert data_b_breach.get("error_code") == "not_found"


register_isolation_spec(
    ToolIsolationSpec(
        name="sales_summary",
        allows_anonymous=False,
        sample_args={"action": "today"},
        custom_isolation_check=_sales_summary_cross_user_isolation,
    )
)


async def _vocab_cross_user_isolation(session_a: ClientSession, session_b: ClientSession) -> None:
    # User A gets word of the day
    res_a = await session_a.call_tool(
        "vocab",
        {"action": "word_of_day", "language": "spanish"},
    )
    data_a = json.loads(getattr(res_a.content[0], "text", "{}"))
    assert data_a.get("ok") is True, f"User A failed to get word of the day: {data_a}"
    uw_id_a = data_a.get("data", {}).get("user_word", {}).get("id")
    assert uw_id_a, "Failed to get user_word_id from User A's response"

    # User B attempts to grade User A's word_id: must return not_found
    res_b_breach = await session_b.call_tool(
        "vocab",
        {"action": "grade", "user_word_id": uw_id_a, "rating": "good"},
    )
    data_b_breach = json.loads(getattr(res_b_breach.content[0], "text", "{}"))
    assert data_b_breach.get("ok") is False
    assert data_b_breach.get("error_code") == "not_found"

    # User A grades their own word: must succeed
    res_a_grade = await session_a.call_tool(
        "vocab",
        {"action": "grade", "user_word_id": uw_id_a, "rating": "good"},
    )
    data_a_grade = json.loads(getattr(res_a_grade.content[0], "text", "{}"))
    assert data_a_grade.get("ok") is True


register_isolation_spec(
    ToolIsolationSpec(
        name="vocab",
        allows_anonymous=False,
        sample_args={"action": "stats"},
        custom_isolation_check=_vocab_cross_user_isolation,
    )
)


async def _language_practice_cross_user_isolation(
    session_a: ClientSession, session_b: ClientSession
) -> None:
    # User A starts conversation
    res_a = await session_a.call_tool(
        "language_practice",
        {"action": "start_conversation", "language": "spanish", "scenario": "ordering_food"},
    )
    data_a = json.loads(getattr(res_a.content[0], "text", "{}"))
    assert data_a.get("ok") is True, f"User A failed to start conversation: {data_a}"
    s_id_a = data_a.get("data", {}).get("session", {}).get("id")
    assert s_id_a, "Missing session_id for User A"

    # User B attempts to reply to User A's session: must fail with not_found
    res_b_breach = await session_b.call_tool(
        "language_practice",
        {"action": "reply", "session_id": s_id_a, "user_message": "Un cafe por favor"},
    )
    data_b_breach = json.loads(getattr(res_b_breach.content[0], "text", "{}"))
    assert data_b_breach.get("ok") is False
    assert data_b_breach.get("error_code") == "not_found"

    # User A replies to their own session: must succeed
    res_a_reply = await session_a.call_tool(
        "language_practice",
        {"action": "reply", "session_id": s_id_a, "user_message": "Un cafe por favor"},
    )
    data_a_reply = json.loads(getattr(res_a_reply.content[0], "text", "{}"))
    assert data_a_reply.get("ok") is True


register_isolation_spec(
    ToolIsolationSpec(
        name="language_practice",
        allows_anonymous=False,
        sample_args={"action": "translate_explain", "query": "hello", "target_language": "spanish"},
        custom_isolation_check=_language_practice_cross_user_isolation,
    )
)

register_isolation_spec(
    ToolIsolationSpec(
        name="transit_status",
        allows_anonymous=True,
        sample_args={"action": "status", "line": "yellow"},
    )
)
